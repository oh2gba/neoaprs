// Every tab drawn in the pseudo-locale (src/i18n/pseudo.ts, English made long and accented): a text of the page that comes through the catalogue is bracketed and accented, so any text node or attribute that still equals a message of the
// English catalogue was written into the page instead. The test grows with the conversion: it looks for the ids that exist, and what is not yet converted is not an id.
import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { en } from "@/i18n/en";
import { setLocale } from "@/i18n";
import { texts, type Message } from "@/i18n/message";
import { TAB_IDS } from "@/lib/layout";
import { open, tabButton, useAppHarness } from "@/test/app";
import { configValues, status, tncState } from "@/test/fixtures";

useAppHarness();

const escape = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
/** Each English text of the catalogue as what it would look like on the page: a value is any text. A message of less than three letters is not looked for (a symbol, a unit), nor one made mostly of values ("{span} ago" would be any text that ends in "ago"). */
const ENGLISH = Object.values(en as Record<string, Message>)
  .flatMap(texts)
  .filter((text) => text.replace(/\{\w+\}/g, "").trim().length >= (/\{\w+\}/.test(text) ? 8 : 3))
  .map((text) => ({
    text,
    re: new RegExp(
      `^${text
        .split(/(\{\{|\}\}|\{\w+\})/)
        .map((p) => (p === "{{" ? "\\{" : p === "}}" ? "\\}" : /^\{\w+\}$/.test(p) ? ".+" : escape(p)))
        .join("")}$`,
    ),
  }));

/** Words of components that are not converted yet (src/i18n/unconverted.json) that are the same as a message that is: they show in English in the pseudo-locale. Whoever converts the component takes its word out; a word that no tab shows any more fails the test. */
const STILL_ENGLISH = [
  "Antenna",
  "Beacon",
  "Call",
  "Close",
  "Comment",
  "Digipeater",
  "Email",
  "Kind",
  "Map",
  "Packet",
  "Path",
  "Position",
  "Speed",
  "Station",
  "Status",
  "Text",
  "direct",
];
const shown = new Set<string>();

const ATTRIBUTES = ["title", "aria-label", "placeholder", "alt", "label"];

/** The text nodes and the attributes of a page that read as an English message of the catalogue. */
function untranslated(root: HTMLElement): string[] {
  const found: string[] = [];
  const seen = (text: string): void => {
    const plain = text.trim().replace(/\s+/g, " ");
    if (plain !== "" && ENGLISH.some((e) => e.re.test(plain))) found.push(plain);
  };
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) seen(node.textContent ?? "");
  for (const el of root.querySelectorAll("*")) for (const a of ATTRIBUTES) if (el.hasAttribute(a)) seen(el.getAttribute(a) ?? "");
  return found;
}

describe("the page in the pseudo-locale", () => {
  for (const tab of TAB_IDS) {
    it(`draws the ${tab} tab with every converted text from the catalogue`, async () => {
      setLocale("en-XA");
      localStorage.setItem("NeoAPRS.tab", tab);
      const { wrapper, socket } = await open();
      socket.say({ type: "state", topic: "tnc", rev: 5, value: tncState({ state: "waiting", problem: "no radio found", describe: "waiting" }) });
      socket.say({ type: "state", topic: "config", rev: 5, value: configValues({ "station/call": "" }) });
      socket.say(status({ update: { version: "9.9.9", message: "", url: "https://example.org/" } }));
      await flushPromises();
      expect(wrapper.findAll("[role='tab']").length).toBe(TAB_IDS.length);
      expect(wrapper.findAll("[role='tab']").every((b) => b.text().startsWith("[!!"))).toBe(true);
      expect(wrapper.find(".appheader button.nocall").text()).toMatch(/^\[!! /);
      expect(wrapper.find(".panelfoot button.status").text()).toMatch(/^\[!! /);
      expect(wrapper.find(".panelfoot button.update").text()).toMatch(/^\[!! .*9\.9\.9/);
      expect(tabButton(wrapper, "[!!")).toBeDefined();
      const english = untranslated(document.body);
      for (const text of english) shown.add(text);
      expect(english.filter((text) => !STILL_ENGLISH.includes(text))).toEqual([]);
    });
  }

  it("has no word in its list of English words that the page does not show any more", () => {
    expect(STILL_ENGLISH.filter((text) => !shown.has(text))).toEqual([]);
  });

  it("shows the language field, with the languages by their own names, and a text written by hand would show as English", async () => {
    setLocale("en-XA");
    localStorage.setItem("NeoAPRS.tab", "settings");
    const { wrapper } = await open();
    expect(wrapper.find("label[for='language']").text()).toMatch(/^\[!! /);
    expect(wrapper.findAll("#language option").map((o) => o.text())).toContain("English");
    document.body.insertAdjacentHTML("beforeend", "<p>Show the panel</p>");
    expect(untranslated(document.body).filter((text) => !STILL_ENGLISH.includes(text))).toEqual(["Show the panel"]);
  });
});
