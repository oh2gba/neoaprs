// What the copy menu (components/CopyMenu.vue, composables/useCopyMenu.ts) offers to copy: a call,
// message, packet, email address or object name, each with its own label; and where a
// keyboard-opened menu stands.

type CopyKind = "call" | "message" | "packet" | "address" | "name";

export interface CopyItem {
  kind: CopyKind;
  text: string;
}

/**
 * How much of a copied text the toast repeats: a call or address whole, a long message cut short.
 */
export const SAID_MAX = 40;

/**
 * The text as the toast says it was copied: at most SAID_MAX characters, an ellipsis for the rest.
 */
export function saidText(text: string): string {
  const line = text.replace(/\s+/g, " ").trim();
  return line.length <= SAID_MAX ? line : `${line.slice(0, SAID_MAX - 1).trimEnd()}…`;
}

/**
 * Where a menu opens for `event` on `element`: at the pointer, or for the menu key (no pointer: the
 * browser says 0, 0) a little inside the element's left edge.
 */
export function menuPoint(event: { clientX: number; clientY: number }, element: Element): { x: number; y: number } {
  if (event.clientX !== 0 || event.clientY !== 0) return { x: event.clientX, y: event.clientY };
  const box = element.getBoundingClientRect();
  return { x: box.left + 24, y: box.bottom };
}
