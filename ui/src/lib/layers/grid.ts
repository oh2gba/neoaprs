// The locator grid for the part of the map in view: the lines of the Maidenhead cells and one name in each (lib/locator.ts gives the names, so they are what Copy locator gives). Fields (20 by 10 degrees) far out,
// squares (2 by 1) from zoom 5, subsquares (5 by 2.5 minutes) from zoom 10; never more than 400 named cells, else the next coarser step. A square is wider than the view near zoom 8 and 9, where its subsquares are
// too many to name: their lines are drawn there without names, once a subsquare is wide enough on the screen to be told apart. Each name stands in the middle of the part of its cell that is in view, so the cell
// under the middle of the view always has its name in sight; a sliver of a cell at the edge has none. A view across the date line is gridded in both copies of the world it shows.
import { positionToLocator } from "@/lib/locator";

/** The part of the map in view, in degrees, and its zoom. */
export interface GridView {
  west: number;
  south: number;
  east: number;
  north: number;
  zoom: number;
}

export type GridStep = "field" | "square" | "subsquare";

interface Step {
  step: GridStep;
  /** degrees of longitude and of latitude */
  w: number;
  h: number;
  /** the characters of the locator that name a cell */
  chars: number;
  /** the zoom it is named from */
  from: number;
}

const STEPS: readonly Step[] = [
  { step: "field", w: 20, h: 10, chars: 2, from: -Infinity },
  { step: "square", w: 2, h: 1, chars: 4, from: 5 },
  { step: "subsquare", w: 2 / 24, h: 1 / 24, chars: 6, from: 10 },
];

export const MAX_CELLS = 400;
/** the narrowest a cell of lines without names is drawn, in pixels */
const LINE_PX = 12;
/** the least of a cell that is given its name, in pixels (a sliver at the edge has none) */
const NAME_PX = { w: 36, h: 16 };
const TILE_PX = 512; // the map engine's
const MERCATOR_LAT = 85.0511;

type LonLat = [number, number];
export type GridFeature =
  | { type: "Feature"; properties: { rank: 0 | 1 }; geometry: { type: "LineString"; coordinates: LonLat[] } }
  | { type: "Feature"; properties: { name: string }; geometry: { type: "Point"; coordinates: LonLat } };
export interface GridCollection {
  type: "FeatureCollection";
  features: GridFeature[];
}

export const NO_GRID: GridCollection = { type: "FeatureCollection", features: [] };

const worldPx = (zoom: number): number => TILE_PX * 2 ** zoom;
const mercY = (lat: number): number => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
const widthPx = (degrees: number, zoom: number): number => (degrees / 360) * worldPx(zoom);
const heightPx = (south: number, north: number, zoom: number): number => ((mercY(north) - mercY(south)) / (2 * Math.PI)) * worldPx(zoom);

/** A part of the view inside one copy of the world, in that copy's degrees (-180..180), and how far east of it the copy is drawn. */
interface Piece {
  view: GridView;
  shift: number;
}

/** The view cut into its parts inside the copies of the world it shows (the map repeats the world sideways, and a view across the date line shows two of them) and inside the mercator's latitudes. */
function pieces(given: GridView): Piece[] {
  const south = Math.max(-MERCATOR_LAT, given.south);
  const north = Math.min(MERCATOR_LAT, given.north);
  if (![given.west, given.east, south, north].every(Number.isFinite) || !(given.east > given.west && north > south)) return [];
  const out: Piece[] = [];
  for (let shift = 360 * Math.floor((given.west + 180) / 360); shift - 180 < given.east; shift += 360) {
    const west = Math.max(-180, given.west - shift);
    const east = Math.min(180, given.east - shift);
    if (east > west) out.push({ view: { west, south, east, north, zoom: given.zoom }, shift });
  }
  return out;
}

/** The first and the last column and row of a step's cells that the view touches. */
function span(view: GridView, step: Step): { c0: number; c1: number; r0: number; r1: number } {
  const last = (count: number) => count - 1;
  const col = (lon: number) => Math.min(last(360 / step.w), Math.floor((lon + 180) / step.w + 1e-9));
  const row = (lat: number) => Math.min(last(180 / step.h), Math.floor((lat + 90) / step.h + 1e-9));
  return { c0: col(view.west), c1: col(view.east), r0: row(view.south), r1: row(view.north) };
}

export function cellCount(view: GridView, step: GridStep): number {
  const one = STEPS.find((s) => s.step === step) ?? STEPS[0];
  if (!one) return 0;
  return pieces(view).reduce((sum, { view: part }) => {
    const { c0, c1, r0, r1 } = span(part, one);
    return sum + (c1 - c0 + 1) * (r1 - r0 + 1);
  }, 0);
}

/** The step whose cells are named: the finest the zoom allows that has at most 400 cells in view (in all the copies of the world it shows together). */
export function namedStep(view: GridView): GridStep {
  const allowed = STEPS.filter((s) => view.zoom >= s.from).reverse();
  return allowed.find((s) => cellCount(view, s.step) <= MAX_CELLS)?.step ?? "field";
}

const line = (rank: 0 | 1, coordinates: LonLat[]): GridFeature => ({ type: "Feature", properties: { rank }, geometry: { type: "LineString", coordinates } });

/** The lines of a step across a piece of the view, those on the lines of `skip` left out (they are drawn already), in the copy of the world the piece is drawn in. */
function lines({ view, shift }: Piece, step: Step, rank: 0 | 1, skip?: Step): GridFeature[] {
  const { c0, c1, r0, r1 } = span(view, step);
  const on = (n: number, size: number, coarse?: number) => coarse !== undefined && Math.abs(Math.round((n * size) / coarse) - (n * size) / coarse) < 1e-6;
  const out: GridFeature[] = [];
  for (let c = c0 + 1; c <= c1; c++)
    if (!on(c, step.w, skip?.w))
      out.push(
        line(rank, [
          [shift - 180 + c * step.w, view.south],
          [shift - 180 + c * step.w, view.north],
        ]),
      );
  for (let r = r0 + 1; r <= r1; r++)
    if (!on(r, step.h, skip?.h))
      out.push(
        line(rank, [
          [shift + view.west, -90 + r * step.h],
          [shift + view.east, -90 + r * step.h],
        ]),
      );
  return out;
}

/** A name in each cell of a piece, in the middle of its part in view; none on a sliver, but the cell under the middle of the view (`middle`, in the view's degrees) always has its name. */
function names({ view, shift }: Piece, step: Step, middle: { lon: number; lat: number }): GridFeature[] {
  const { c0, c1, r0, r1 } = span(view, step);
  const out: GridFeature[] = [];
  for (let c = c0; c <= c1; c++) {
    for (let r = r0; r <= r1; r++) {
      const west = Math.max(view.west, -180 + c * step.w);
      const east = Math.min(view.east, -180 + (c + 1) * step.w);
      const south = Math.max(view.south, -90 + r * step.h);
      const north = Math.min(view.north, -90 + (r + 1) * step.h);
      const holdsMiddle = middle.lon - shift >= west && middle.lon - shift <= east && middle.lat >= south && middle.lat <= north;
      if (!holdsMiddle && (widthPx(east - west, view.zoom) < NAME_PX.w || heightPx(south, north, view.zoom) < NAME_PX.h)) continue;
      const name = positionToLocator(-90 + (r + 0.5) * step.h, -180 + (c + 0.5) * step.w).slice(0, step.chars);
      out.push({ type: "Feature", properties: { name }, geometry: { type: "Point", coordinates: [shift + (west + east) / 2, (south + north) / 2] } });
    }
  }
  return out;
}

/** What the grid draws for a view: the lines and names of its named step, and the subsquares' lines without names where squares are named and a subsquare is wide enough to be seen. A view across the date line
 * is drawn piece by piece, each in the copy of the world it shows, and the date line between two pieces is a line of every step. */
export function gridFeatures(view: GridView): GridCollection {
  const parts = pieces(view);
  const first = parts[0];
  if (!first) return NO_GRID;
  const index = STEPS.findIndex((s) => s.step === namedStep(view));
  const step = STEPS[index];
  if (!step) return NO_GRID;
  const finer = STEPS[index + 1];
  const unnamed = finer && finer.step === "subsquare" && widthPx(finer.w, view.zoom) >= LINE_PX ? finer : undefined;
  const middle = { lon: (view.west + view.east) / 2, lat: (first.view.south + first.view.north) / 2 };
  const features: GridFeature[] = [];
  for (const part of parts) {
    if (part !== first)
      features.push(
        line(0, [
          [part.shift - 180, part.view.south],
          [part.shift - 180, part.view.north],
        ]),
      );
    features.push(...lines(part, step, 0), ...names(part, step, middle));
    if (unnamed) features.push(...lines(part, unnamed, 1, step));
  }
  return { type: "FeatureCollection", features };
}
