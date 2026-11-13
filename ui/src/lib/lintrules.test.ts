// @vitest-environment node
// The rules of eslint.config.js that keep what a station sent a text on the page, shown at work on made-up sources: every way to make markup or code of a text is refused where it is written (a template, a script,
// the service worker), what only sets a text is let through, and a test keeps reading the markup a component made. A rule that nobody has seen refusing anything is a guess, and `npm run lint` on a clean tree
// says nothing about it. Each source is linted as the content of a file that exists, because the typed rules ask the TypeScript project for the file they are given.
import { ESLint } from "eslint";
import { expect, it } from "vitest";

const SLOW = 60_000; // the first source waits for ESLint to read the configuration and the TypeScript project
const RULES = [
  "vue/no-v-html",
  "vue/no-restricted-v-bind",
  "vue/no-restricted-static-attribute",
  "vue/no-restricted-syntax",
  "no-restricted-properties",
  "no-restricted-syntax",
  "no-eval",
  "no-new-func",
  "no-implied-eval",
  "@typescript-eslint/no-implied-eval",
];
type Case = [line: string, refused: boolean];

const eslint = new ESLint();

/** The lines among `cases` that ESLint refuses by one of the rules above when `before`, the lines and `after` are the content of `file`. A source that does not parse fails here: it would show nothing. */
async function refused(file: string, before: string[], cases: Case[], after: string[]): Promise<string[]> {
  const lines = [...before, ...cases.map(([line]) => line), ...after];
  const [result] = await eslint.lintText(lines.join("\n") + "\n", { filePath: file });
  expect(result.messages.filter((message) => message.fatal || message.ruleId === "vue/no-parsing-error")).toEqual([]);
  const hit = new Set(result.messages.filter((message) => message.severity === 2 && RULES.includes(message.ruleId ?? "")).map((message) => message.line));
  return lines.filter((_line, index) => hit.has(index + 1));
}

function expected(cases: Case[]): string[] {
  return cases.filter(([, isRefused]) => isRefused).map(([line]) => line);
}

const TEMPLATE: Case[] = [
  ['<p v-html="text" />', true],
  ['<p :innerHTML="text" />', true],
  ['<p .innerHTML="text" />', true],
  ['<p :inner-h-t-m-l="text" />', true],
  ['<p :outerHTML="text" />', true],
  ['<iframe :srcdoc="text" />', true],
  ['<iframe srcdoc="<p>x</p>" />', true],
  // the object of a binding, which the rule for a binding's name does not read
  ['<p v-bind="{ innerHTML: text }" />', true],
  ["<p v-bind=\"{ 'outerHTML': text }\" />", true],
  ['<iframe v-bind="{ srcdoc: text }" />', true],
  ['<p v-bind="{ [`innerHTML`]: text }" />', true],
  ['<p v-bind="{ title: text, ...{ innerHTML: text } }" />', true],
  ["<p v-bind=\"{ '.innerHTML': text }\" />", true],
  // the same object bound with the bare colon, which the parser reads as an attribute named ":"
  ['<p :="{ innerHTML: text }" />', true],
  ['<iframe :="{ srcdoc: text }" />', true],
  // a name written between brackets, and a handler that sets or calls the property itself
  ['<p :[`innerHTML`]="text" />', true],
  ['<p @click="($event.target as HTMLElement).innerHTML = text" />', true],
  ["<p @click=\"$el['outerHTML'] = text\" />", true],
  ["<p @click=\"$el.insertAdjacentHTML('beforeend', text)\" />", true],
  ["<p @click=\"$el.setAttribute('srcdoc', text)\" />", true],
  // a text that stays a text
  ['<p v-bind="{ title: text }" />', false],
  ['<p :title="text">{{ text }}</p>', false],
  ['<p @click="$el.textContent = text" />', false],
];

const SCRIPT: Case[] = [
  ["  element.innerHTML = text;", true],
  ["  element.outerHTML = text;", true],
  ['  element.insertAdjacentHTML("beforeend", text);', true],
  ["  frame.srcdoc = text;", true],
  ['  frame.setAttribute("srcdoc", text);', true],
  ["  document.write(text);", true],
  ["  Object.assign(element, { innerHTML: text });", true],
  ["  Object.assign(element, { [`outerHTML`]: text });", true],
  ['  Object.assign(element, { ".innerHTML": text });', true],
  ["  eval(text);", true],
  ["  new Function(text)();", true],
  ["  setTimeout(text, 1);", true],
  ["  element.textContent = text;", false],
  ["  Object.assign(element, { title: text });", false],
];

const WORKER: Case[] = [
  ["  const box = { innerHTML: event.data };", true],
  ["  eval(event.data);", true],
  ["  new Function(event.data)();", true],
  ['  setTimeout("x()", 1);', true],
  ["  event.waitUntil(Promise.resolve(box));", false],
];

const TEST: Case[] = [
  ['  box.innerHTML = "<b>x</b>";', false],
  ["  const made = { innerHTML: box.outerHTML };", false],
  ["  eval(made.innerHTML);", true],
];

it(
  "refuses in a template every way to make markup of a text, the object of a binding among them",
  async () => {
    const before = ['<script setup lang="ts">', "defineProps<{ text: string }>();", "</script>", "<template>", "<div>"];
    expect(await refused("src/App.vue", before, TEMPLATE, ["</div>", "</template>"])).toEqual(expected(TEMPLATE));
  },
  SLOW,
);

it(
  "refuses in a script the ways to make markup or code of a text",
  async () => {
    const before = ["export function sinks(element: HTMLElement, frame: HTMLIFrameElement, text: string): void {"];
    expect(await refused("src/main.ts", before, SCRIPT, ["}"])).toEqual(expected(SCRIPT));
  },
  SLOW,
);

it(
  "refuses the same in the service worker, which is linted without the types",
  async () => {
    expect(await refused("sw/sw.js", ['self.addEventListener("message", (event) => {'], WORKER, ["});"])).toEqual(expected(WORKER));
  },
  SLOW,
);

it(
  "lets a test read the markup a component made, and still refuses eval there",
  async () => {
    const before = ['const box = document.createElement("div");', "export function reads(): void {"];
    expect(await refused("src/lib/lintrules.test.ts", before, TEST, ["}"])).toEqual(expected(TEST));
  },
  SLOW,
);
