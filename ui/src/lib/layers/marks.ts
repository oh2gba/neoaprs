// The drawn shapes of the map's layers, as SVG path data on a square of 16 by 16 pointing north: the mark of each row of the Layers box (components/LayerMark.vue) and the images the map draws an aircraft or a ship with,
// so that the box is the legend. A mark is filled or stroked, in the token of what it stands for on the map (the tracks' blue, the label colour of the circle and the grid, the layers' own colour of the things).

/** A shape of the box and the map. */
export type MarkName = "layers" | "track" | "circle" | "grid" | "dart" | "hull" | "diamond";

export interface Mark {
  /** the path on a square of 16 by 16, pointing north */
  readonly d: string;
  /** filled, or a line of 1.5 */
  readonly fill: boolean;
  /** the dashes of a line, as `stroke-dasharray` */
  readonly dash?: string;
  /** the colour token it is drawn in (styles/tokens.css) */
  readonly token: string;
}

/** The square every mark is drawn on. */
export const MARK_SIZE = 16;

export const MARKS: Readonly<Record<MarkName, Mark>> = {
  /** the Layers button: three sheets one over the other */
  layers: { d: "M8 2 L15 5.5 L8 9 L1 5.5 Z M1 8.5 L8 12 L15 8.5 M1 11.5 L8 15 L15 11.5", fill: false, token: "--map-control-ink" },
  /** a track: a line that wanders */
  track: { d: "M1.5 12.5 C4 4 7.5 14 10 7 S13.5 3 14.5 4", fill: false, token: "--map-track" },
  /** the ALOHA circle: a dashed ring */
  circle: { d: "M8 2 A6 6 0 1 1 7.99 2 Z", fill: false, dash: "2.6 2", token: "--map-label" },
  /** the locator grid: two lines across two */
  grid: { d: "M5.5 1 V15 M10.5 1 V15 M1 5.5 H15 M1 10.5 H15", fill: false, token: "--map-label" },
  /** an aircraft: a dart turned to where it heads */
  dart: { d: "M8 1 L13.5 14.5 L8 11.5 L2.5 14.5 Z", fill: true, token: "--map-layer" },
  /** a ship: a hull seen from above, its bow ahead */
  hull: { d: "M8 1 C10.5 3.5 11.5 6.5 11.5 9.5 L11.5 15 L4.5 15 L4.5 9.5 C4.5 6.5 5.5 3.5 8 1 Z", fill: true, token: "--map-layer" },
  /** a thing that gives no direction */
  diamond: { d: "M8 3.5 L12.5 8 L8 12.5 L3.5 8 Z", fill: true, token: "--map-layer" },
};
