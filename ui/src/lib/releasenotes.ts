// The release notes as the update dialog shows them (components/UpdateDialog.vue): a section of the changelog is markdown of the plain kind the project writes, and this reads it into blocks (a heading, a paragraph, a bullet) of parts (text, bold, code),
// which the dialog draws itself; a link is its text. Anything else is text as it stands. And which of two versions is the newer, as the daemon tells it, for the line the page shows once after an update (composables/useWhatsNew.ts).

export interface NotePart {
  text: string;
  bold?: boolean;
  code?: boolean;
}

export interface NoteBlock {
  kind: "heading" | "paragraph" | "bullet";
  parts: NotePart[];
}

const INLINE = /\*\*([^*]+)\*\*|`([^`]+)`/g;
const LINK = /\[([^\]]+)\]\([^)]*\)/g;

/** The parts of one line: `**bold**` and `code` set apart, a link reduced to its text. */
export function noteParts(line: string): NotePart[] {
  const text = line.replace(LINK, "$1");
  const parts: NotePart[] = [];
  let at = 0;
  for (const match of text.matchAll(INLINE)) {
    if (match.index > at) parts.push({ text: text.slice(at, match.index) });
    if (match[1] !== undefined) parts.push({ text: match[1], bold: true });
    else if (match[2] !== undefined) parts.push({ text: match[2], code: true });
    at = match.index + match[0].length;
  }
  if (at < text.length) parts.push({ text: text.slice(at) });
  return parts;
}

/** The blocks of a section: a `#` heading of any depth, a `- ` or `* ` bullet, and the lines between blank lines as one paragraph. */
export function noteBlocks(text: string): NoteBlock[] {
  const blocks: NoteBlock[] = [];
  let paragraph: string[] = [];
  const flush = (): void => {
    if (paragraph.length > 0) blocks.push({ kind: "paragraph", parts: noteParts(paragraph.join(" ")) });
    paragraph = [];
  };
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    const heading = /^#+\s+(.*)$/.exec(line);
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    if (line === "") flush();
    else if (heading?.[1] !== undefined) {
      flush();
      blocks.push({ kind: "heading", parts: noteParts(heading[1]) });
    } else if (bullet?.[1] !== undefined) {
      flush();
      blocks.push({ kind: "bullet", parts: noteParts(bullet[1]) });
    } else paragraph.push(line);
  }
  flush();
  return blocks;
}

const VERSION = /^\d+(\.\d+){0,3}([-+][0-9A-Za-z.]+)?$/;
const SEPARATORS = /[.\-+]/;
const DIGITS = /^\d+$/;

/** A version as the daemon names one ("0.12.0", "1.0.0-rc1"), not an empty or a made-up text. */
export const isVersion = (text: string): boolean => VERSION.test(text.trim());

/** -1, 0 or 1 as `a` is older than, the same as or newer than `b`, the daemon's way (neoaprs/versions.py): "0.10.0" is newer than "0.9.0", a missing part counts as 0, and "1.0.0-rc1" is older than "1.0.0". */
export function compareVersions(a: string, b: string): number {
  const left = a.trim().split(SEPARATORS).filter(Boolean);
  const right = b.trim().split(SEPARATORS).filter(Boolean);
  for (let i = 0; i < Math.max(left.length, right.length); i++) {
    const x = left[i] ?? "0";
    const y = right[i] ?? "0";
    const xNumber = DIGITS.test(x);
    const yNumber = DIGITS.test(y);
    // a number comes after a suffix: "1.0.0-rc1" sorts before "1.0.0"
    if (xNumber && yNumber) {
      if (Number(x) !== Number(y)) return Number(x) < Number(y) ? -1 : 1;
    } else if (xNumber !== yNumber) return xNumber ? 1 : -1;
    else if (x.toLowerCase() !== y.toLowerCase()) return x.toLowerCase() < y.toLowerCase() ? -1 : 1;
  }
  return 0;
}
