// Lines across the date line. A longitude pair that jumps by more than half the globe is the
// short way over 180 degrees, so a line carries its longitudes on past 180 (or -180) instead of
// wrapping them, and the map draws it as one short stretch.

type LonLat = readonly [number, number];

/** The signed longitude difference from `from` to `to`, the short way round, -180 to 180. */
export function eastOf(from: number, to: number): number {
  return ((((to - from) % 360) + 540) % 360) - 180;
}

/** A longitude brought into -180 to 180. */
export function wrapLon(lon: number): number {
  if (lon >= -180 && lon <= 180) return lon;
  return ((((lon + 180) % 360) + 360) % 360) - 180;
}

/**
 * The points of a line with the longitudes running on past the date line, so no stretch is
 * longer than half the globe.
 */
export function unwrapLine<T extends LonLat>(points: readonly T[]): [number, number][] {
  let shift = 0;
  return points.map(([lon, lat], i): [number, number] => {
    const before = points[i - 1];
    if (before !== undefined && Math.abs(lon - before[0]) > 180) shift += lon < before[0] ? 360 : -360;
    return [lon + shift, lat];
  });
}
