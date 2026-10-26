// The strokes the pictures of the (i) notes are drawn with, as the `d` of a path: an arrow, and the arcs that stand for radio waves. Every number is rounded to a tenth so that the markup stays short.
const round = (n: number): number => Math.round(n * 10) / 10;

/** A line from (x1, y1) to (x2, y2) with an open arrow head of `head` px at the end. */
export function arrow(x1: number, y1: number, x2: number, y2: number, head = 5): string {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const wing = (turn: number): string => `${round(x2 - head * Math.cos(angle + turn))} ${round(y2 - head * Math.sin(angle + turn))}`;
  return `M${x1} ${y1}L${x2} ${y2}M${wing(0.5)}L${x2} ${y2}L${wing(-0.5)}`;
}

/** `count` arcs that open away from (x, y) towards `angle` (degrees, 0 is to the right, 90 down), the first at `start` px and the next every `gap` px: radio waves. */
export function waves(x: number, y: number, angle: number, count = 3, start = 9, gap = 6): string {
  const spread = 0.62;
  const point = (radius: number, turn: number): string => {
    const a = (angle * Math.PI) / 180 + turn;
    return `${round(x + radius * Math.cos(a))} ${round(y + radius * Math.sin(a))}`;
  };
  return Array.from({ length: count }, (_, i) => {
    const radius = start + i * gap;
    return `M${point(radius, -spread)}A${radius} ${radius} 0 0 1 ${point(radius, spread)}`;
  }).join("");
}
