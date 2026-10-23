// Finds the words of a component's template that are written into it instead of coming from the catalogue (src/i18n): the guard rail of the translation (src/i18n/literals.test.ts).
//
// What counts as a literal:
//  - a text node of the template, and the value of a plain `title`, `placeholder`, `aria-label`, `label` or `alt` attribute, that has a word in it (two letters in a row) once the words that are the same in every language
//    are taken out (ALLOWED: the brand, units);
//  - in an interpolation `{{ }}` and in a bound `:title="..."` (and the other four), a string that has a word in it and either a space or a capital first letter (a lowercase single word there is mostly an identifier:
//    `state === 'acked'`); the id inside `t("...")` is not a literal.
import { parse } from "vue/compiler-sfc";

/** Words that are not translated: the brand and the units. */
const ALLOWED = ["NeoAPRS", "APRS", "km", "hPa", "mm", "MB", "kB", "GB", "MHz", "kHz", "Hz", "min"];
const ATTRIBUTES = ["title", "placeholder", "aria-label", "label", "alt"];
const WORD = /\p{L}{2,}/u;
const STRING = /'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"|`((?:[^`\\$]|\\.|\$(?!\{))*)`/g;

export interface Literal {
  line: number;
  text: string;
}

function hasWords(text: string): boolean {
  let rest = text;
  for (const word of ALLOWED) rest = rest.replaceAll(new RegExp(`(?<![\\p{L}])${word}(?![\\p{L}])`, "gu"), " ");
  return WORD.test(rest);
}

/** The strings of an expression that read like text (not the id of a `t("...")`). */
function stringsOf(expression: string): string[] {
  const without = expression.replace(/\bt\(\s*(['"`])[^'"`]*\1/g, "t(");
  return [...without.matchAll(STRING)].map((m) => m[1] ?? m[2] ?? m[3] ?? "").filter((s) => hasWords(s) && (/\s/.test(s.trim()) || /^\p{Lu}/u.test(s.trim())));
}

interface Node {
  type: number;
  tag?: string;
  content?: string | { content: string };
  props?: Property[];
  children?: Node[];
  loc: { start: { line: number } };
}
interface Property {
  type: number;
  name: string;
  value?: { content: string };
  arg?: { content: string };
  exp?: { content: string };
  loc: { start: { line: number } };
}

const ELEMENT = 1;
const TEXT = 2;
const INTERPOLATION = 5;
const ATTRIBUTE = 6;
const DIRECTIVE = 7;

/** The literals of the attributes of an element. */
function inProps(props: Property[], found: Literal[]): void {
  for (const p of props) {
    const line = p.loc.start.line;
    if (p.type === ATTRIBUTE && ATTRIBUTES.includes(p.name) && p.value && hasWords(p.value.content)) found.push({ line, text: p.value.content });
    if (p.type === DIRECTIVE && p.name === "bind" && p.arg && ATTRIBUTES.includes(p.arg.content) && p.exp)
      for (const text of stringsOf(p.exp.content)) found.push({ line, text });
  }
}

function walk(node: Node, found: Literal[]): void {
  const line = node.loc.start.line;
  if (node.type === TEXT && typeof node.content === "string" && hasWords(node.content)) found.push({ line, text: node.content.trim().replace(/\s+/g, " ") });
  if (node.type === INTERPOLATION && typeof node.content === "object") for (const text of stringsOf(node.content.content)) found.push({ line, text });
  if (node.type !== ELEMENT) return;
  inProps(node.props ?? [], found);
  for (const child of node.children ?? []) walk(child, found);
}

/** The literals of the template of a single-file component. */
export function findLiterals(source: string): Literal[] {
  const ast = parse(source).descriptor.template?.ast as unknown as Node | undefined;
  const found: Literal[] = [];
  for (const child of ast?.children ?? []) walk(child, found);
  return found;
}
