// The part of the world where the sun is down, for the map's Day and night layer: the sun's place
// from the clock (the Astronomical Almanac's low-precision formulas, about 0.01 degrees) and the
// area where its altitude is below a limit, as polygons of longitude and latitude within the
// map's own latitudes. Degrees throughout.

/** The sun's altitude at sunrise and sunset. */
export const SUN_DOWN = -0.833;
/** The sun's altitude at the end of civil twilight. */
export const TWILIGHT_END = -6;
/** The latitude at which the map ends. */
export const MAX_LAT = 85.0511;

/** The point under the sun, the longitude in (-180, 180]. */
export interface Sun {
  lat: number;
  lon: number;
}

const RAD = Math.PI / 180;
const DEG = 180 / Math.PI;
const MS_PER_DAY = 86400000;
const UNIX_EPOCH_JD = 2440587.5;
const J2000_JD = 2451545;

const wrap = (lon: number): number => {
  const wrapped = ((((lon + 180) % 360) + 360) % 360) - 180;
  return wrapped === -180 ? 180 : wrapped;
};

export function sunAt(ms: number): Sun {
  const n = ms / MS_PER_DAY + UNIX_EPOCH_JD - J2000_JD;
  const meanLon = 280.46 + 0.9856474 * n;
  const anomaly = (357.528 + 0.9856003 * n) * RAD;
  const lambda = (meanLon + 1.915 * Math.sin(anomaly) + 0.02 * Math.sin(2 * anomaly)) * RAD;
  const epsilon = (23.439 - 0.0000004 * n) * RAD;
  const rightAscension = Math.atan2(Math.cos(epsilon) * Math.sin(lambda), Math.cos(lambda)) * DEG;
  const lat = Math.asin(Math.sin(epsilon) * Math.sin(lambda)) * DEG;
  const gmst = 280.46061837 + 360.98564736629 * n;
  return { lat, lon: wrap(rightAscension - gmst) };
}

/**
 * The latitudes on a meridian where the sun is below `below`: one span or none. With
 * sin(alt) = R sin(lat + psi) on a meridian, the dark part is a single arc of that sine.
 */
function darkSpan(sun: Sun, below: number, lon: number): [number, number] | null {
  const delta = sun.lat * RAD;
  const a = Math.sin(delta);
  const b = Math.cos(delta) * Math.cos((lon - sun.lon) * RAD);
  const r = Math.hypot(a, b);
  if (r < 1e-12) return null;
  const k = Math.sin(below * RAD) / r;
  if (k <= -1) return null;
  if (k >= 1) return [-MAX_LAT, MAX_LAT];
  const psi = Math.atan2(b, a);
  const half = Math.PI / 2 + Math.asin(k);
  const centre = Math.atan2(-Math.cos(psi), -Math.sin(psi));
  const lo = Math.max((centre - half) * DEG, -MAX_LAT);
  const hi = Math.min((centre + half) * DEG, MAX_LAT);
  return hi - lo < 1e-9 ? null : [lo, hi];
}

interface Cut {
  lon: number;
  span: [number, number];
}

const COARSE_STEP = 1;
const FINEST_STEP = 1 / 64;
const BISECTIONS = 20;

/**
 * Cuts from `from` (exclusive) to `to` (inclusive), with a cut halfway wherever a span's end
 * moves more than a degree of latitude, so that a steep edge is not a staircase.
 */
function refine(sun: Sun, below: number, from: Cut, to: Cut, out: Cut[]): void {
  const step = to.lon - from.lon;
  const steep = Math.abs(to.span[0] - from.span[0]) > 1 || Math.abs(to.span[1] - from.span[1]) > 1;
  if (step > FINEST_STEP && steep) {
    const lon = from.lon + step / 2;
    const span = darkSpan(sun, below, lon);
    if (span) {
      const middle = { lon, span };
      refine(sun, below, from, middle, out);
      refine(sun, below, middle, to, out);
      return;
    }
  }
  out.push(to);
}

/** The cut where the span vanishes, found from a cut inside towards a longitude outside. */
function edgeCut(sun: Sun, below: number, inside: Cut, outside: number): Cut {
  let cut = inside;
  let far = outside;
  for (let i = 0; i < BISECTIONS; i++) {
    const lon = (cut.lon + far) / 2;
    const span = darkSpan(sun, below, lon);
    if (span) cut = { lon, span };
    else far = lon;
  }
  return cut;
}

/** The runs of longitude over which the dark span exists, as cuts. */
function runsOf(sun: Sun, below: number): Cut[][] {
  const runs: Cut[][] = [];
  let run: Cut[] | null = null;
  let before: { lon: number; span: [number, number] | null } | null = null;
  for (let lon = -180; lon <= 180; lon += COARSE_STEP) {
    const span = darkSpan(sun, below, lon);
    if (span && !run) {
      run = [];
      if (before && !before.span) {
        const edge = edgeCut(sun, below, { lon, span }, before.lon);
        run.push(edge);
        refine(sun, below, edge, { lon, span }, run);
      } else run.push({ lon, span });
    } else if (span && run) {
      const last = run[run.length - 1];
      refine(sun, below, last, { lon, span }, run);
    } else if (!span && run) {
      const last = run[run.length - 1];
      const edge = edgeCut(sun, below, last, lon);
      refine(sun, below, last, edge, run);
      runs.push(run);
      run = null;
    }
    before = { lon, span };
  }
  if (run) runs.push(run);
  return runs;
}

/** The area where the sun is below `below`, as the coordinates of a MultiPolygon. */
function darkArea(sun: Sun, below: number): number[][][][] {
  return runsOf(sun, below)
    .filter((run) => run.length > 1)
    .map((run) => {
      const ring = [
        ...run.map((cut): number[] => [cut.lon, cut.span[1]]),
        ...run.map((cut): number[] => [cut.lon, cut.span[0]]).reverse(),
      ];
      return [[...ring, ring[0]]];
    });
}

export type DayNightCollection = {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    properties: { depth: "twilight" | "night" };
    geometry: { type: "MultiPolygon"; coordinates: number[][][][] };
  }[];
};

export const NO_DAYNIGHT: DayNightCollection = { type: "FeatureCollection", features: [] };

/** The twilight and the night, as the map draws them. */
export function dayNightFeatures(ms: number): DayNightCollection {
  const sun = sunAt(ms);
  const feature = (depth: "twilight" | "night", below: number): DayNightCollection["features"][number] => ({
    type: "Feature",
    properties: { depth },
    geometry: { type: "MultiPolygon", coordinates: darkArea(sun, below) },
  });
  return { type: "FeatureCollection", features: [feature("twilight", SUN_DOWN), feature("night", TWILIGHT_END)] };
}
