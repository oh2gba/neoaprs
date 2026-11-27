// Shapes drawn for the map layers, as SVG path data pointing north, on a 16 by 16 square or an
// aircraft's own box: the mark of each row of the Layers box (components/LayerMark.vue) and the
// images the map draws aircraft and ships with, so that the box is the legend. A mark is filled or
// stroked in the token of what it stands for (styles/tokens.css). An aircraft has the shape of its
// kind (lib/layers/aircraftshapes.ts); the box's aircraft row shows the airliner.
import { AIRCRAFT_SHAPES, type AircraftShape } from "@/lib/layers/aircraftshapes";

export type MarkName =
  "layers" | "track" | "circle" | "grid" | "daynight" | "satellite" | "hull" | "diamond" | AircraftShape;

export interface Mark {
  /** The path on a 16 by 16 square, pointing north. */
  readonly d: string;
  /** Filled, or a line of 1.5. */
  readonly fill: boolean;
  /** The dashes of a line, as `stroke-dasharray`. */
  readonly dash?: string;
  /** The colour token it is drawn in (styles/tokens.css). */
  readonly token: string;
  /** The token of a dark outline round a filled mark (an aircraft's). */
  readonly edge?: string;
  /** The box the path is drawn on, where it is not the 16 square. */
  readonly viewBox?: string;
}

export const MARK_SIZE = 16;

export const MARKS: Readonly<Record<MarkName, Mark>> = {
  /** the Layers button: three sheets one over the other */
  layers: {
    d: "M8 2 L15 5.5 L8 9 L1 5.5 Z M1 8.5 L8 12 L15 8.5 M1 11.5 L8 15 L15 11.5",
    fill: false,
    token: "--map-control-ink",
  },
  /** a track: a line that wanders */
  track: { d: "M1.5 12.5 C4 4 7.5 14 10 7 S13.5 3 14.5 4", fill: false, token: "--map-track" },
  /** the ALOHA circle: a dashed ring */
  circle: { d: "M8 2 A6 6 0 1 1 7.99 2 Z", fill: false, dash: "2.6 2", token: "--map-label" },
  /** the locator grid: two lines across two */
  grid: { d: "M5.5 1 V15 M10.5 1 V15 M1 5.5 H15 M1 10.5 H15", fill: false, token: "--map-label" },
  /** day and night: a disc, its left half filled and its right half a ring */
  daynight: {
    d: "M8 2 A6 6 0 1 1 8 14 A6 6 0 1 1 8 2 Z M8 3.5 V12.5 A4.5 4.5 0 0 0 8 3.5 Z",
    fill: true,
    token: "--map-label",
  },
  /** a satellite: a body between two wings of solar panels */
  satellite: {
    d: "M6 4.5 H10 V11.5 H6 Z M0.5 6 H6 V10 H0.5 Z M10 6 H15.5 V10 H10 Z",
    fill: true,
    token: "--map-satellite",
  },
  /** a ship: a hull seen from above, its bow ahead */
  hull: {
    d: "M8 1 C10.5 3.5 11.5 6.5 11.5 9.5 L11.5 15 L4.5 15 L4.5 9.5 C4.5 6.5 5.5 3.5 8 1 Z",
    fill: true,
    token: "--map-layer",
  },
  /** a thing that gives no direction */
  diamond: { d: "M8 3.5 L12.5 8 L8 12.5 L3.5 8 Z", fill: true, token: "--map-layer" },
  ...aircraftMarks(),
};

/** The aircraft's shapes as marks, filled in the aircraft's colour with its dark outline. */
function aircraftMarks(): Record<AircraftShape, Mark> {
  const entries = Object.entries(AIRCRAFT_SHAPES).map(([name, shape]) => [
    name,
    { d: shape.d, viewBox: shape.viewBox, fill: true, token: "--map-aircraft", edge: "--map-aircraft-edge" },
  ]);
  return Object.fromEntries(entries) as Record<AircraftShape, Mark>;
}

/** The box a mark's path is drawn on, as `viewBox`. */
export const markBox = (mark: Mark): string => mark.viewBox ?? `0 0 ${MARK_SIZE} ${MARK_SIZE}`;

/** The width of an outline that shows 1 px round a mark drawn 16 px wide (half of it under the fill). */
export function edgeWidth(mark: Mark): number {
  const [, , width, height] = markBox(mark).split(" ").map(Number) as [number, number, number, number];
  return (2 * Math.max(width, height)) / MARK_SIZE;
}
