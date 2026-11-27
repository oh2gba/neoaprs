// The project page's script (site/site.js) as far as it shows the board of HF tests and the past
// tests under it: the page's tables say no test is planned and none is past, and when skeds were read
// their rows are the calls, the time (now, for one that has begun) and the dial, each written as
// text. The script is run on a made-up page with its own fetch.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { runInThisContext } from "node:vm";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { NOW } from "@/test/fixtures";

const SITE = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "site");
const SCRIPT = readFileSync(join(SITE, "site.js"), "utf-8");
const hours = (n: number) => `${new Date(NOW + n * 3_600_000).toISOString().slice(0, 19)}Z`;
const row = (call: string, extra: Record<string, unknown> = {}) => ({
  id: "7f3a9c21d4e0",
  call,
  from: hours(2),
  to: hours(4),
  dial: "7.0541 MHz USB",
  note: "Mercury, 10 W",
  ...extra,
});

const PAGE = `<section id="skeds"><table id="sked-board"><tbody><tr><td>No tests planned.</td></tr></tbody></table><table id="sked-past"><tbody><tr><td>No past tests.</td></tr></tbody></table></section>`;

/** The section after the script has read `body` as skeds.json and `past` as skeds-past.json (not found when left out). */
async function run(body: unknown, status = 200, past?: unknown): Promise<HTMLElement> {
  document.body.innerHTML = PAGE;
  const asked: string[] = [];
  vi.stubGlobal("fetch", (url: string) => {
    asked.push(url);
    const sent = url === "skeds-past.json" ? past : body;
    return Promise.resolve({
      ok: url === "skeds-past.json" ? past !== undefined : status === 200,
      json: () => (sent instanceof Error ? Promise.reject(sent) : Promise.resolve(sent)),
    });
  });
  runInThisContext(SCRIPT);
  await flushPromises();
  expect(asked).toContain("skeds.json");
  const section = document.getElementById("skeds");
  if (section === null) throw new Error("no section");
  return section;
}
const cells = (section: HTMLElement, table = "sked-board") =>
  [...section.querySelectorAll(`#${table} tbody tr`)].map((tr) => [...tr.children].map((c) => c.textContent));
const pastCells = (section: HTMLElement) => cells(section, "sked-past");

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("the sked board on the project page", () => {
  it("shows the section with the call, the time in UTC and the dial of each sked to come, nearest first, and never the note", async () => {
    const section = await run({
      v: 1,
      skeds: [row("OH2LAT", { from: hours(30), to: hours(31), dial: "14.1070 MHz USB" }), row("OH2GBA")],
    });
    expect(section.hidden).toBe(false);
    expect(cells(section)).toEqual([
      ["OH2GBA", "Wed 21 Oct 14:00 to 16:00", "7.0541 MHz USB"],
      ["OH2LAT", "Thu 22 Oct 18:00 to 19:00", "14.1070 MHz USB"],
    ]);
    expect(section.textContent).not.toContain("Mercury");
  });

  it("writes the end with its day when the sked runs into the next one", async () => {
    const section = await run({
      v: 1,
      skeds: [row("OH2GBA", { from: "2026-10-21T22:00:00Z", to: "2026-10-22T02:00:00Z" })],
    });
    expect(cells(section)).toEqual([["OH2GBA", "Wed 21 Oct 22:00 to Thu 22 Oct 02:00", "7.0541 MHz USB"]]);
  });

  it("says now for a sked that has begun, with its end, and the end's day when that is another day", async () => {
    const section = await run({
      v: 1,
      skeds: [row("OH2GBA", { from: hours(-1), to: hours(1) }), row("OH2LAT", { from: hours(-1), to: hours(20) })],
    });
    const whens = cells(section).map((c) => c[1]);
    expect(whens[0]).toMatch(/^now to \d\d:\d\d$/);
    expect(whens[1]).toMatch(/^now to (Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{1,2} [A-Z][a-z]{2} \d\d:\d\d$/);
  });

  it("makes skeds with the same times and dial one row that lists the calls", async () => {
    const section = await run({ v: 1, skeds: [row("OH2AAA"), row("OH2BBB"), row("OH2AAA")] });
    expect(cells(section)).toEqual([["OH2AAA, OH2BBB", "Wed 21 Oct 14:00 to 16:00", "7.0541 MHz USB"]]);
  });

  it("keeps the page's own row, No tests planned, when no sked to come was read", async () => {
    for (const body of [
      { v: 1, skeds: [] },
      { v: 1, skeds: [row("OH2OLD", { from: hours(-4), to: hours(-2) })] },
      { v: 2, skeds: [row("OH2GBA")] },
      { skeds: [row("OH2GBA")] },
      { v: 1, skeds: "OH2GBA" },
      null,
      "text",
      [],
    ]) {
      const section = await run(body);
      expect(section.hidden, JSON.stringify(body)).toBe(false);
      expect(section.querySelector("#sked-board tbody")?.textContent, JSON.stringify(body)).toBe("No tests planned.");
    }
  });

  it("keeps the page's own row when the file cannot be read: not found, not JSON, no network", async () => {
    const own = (section: HTMLElement | null) => section?.querySelector("#sked-board tbody")?.textContent;
    expect(own(await run({ v: 1, skeds: [row("OH2GBA")] }, 404))).toBe("No tests planned.");
    expect(own(await run(new Error("not json")))).toBe("No tests planned.");
    document.body.innerHTML = PAGE;
    vi.stubGlobal("fetch", () => Promise.reject(new Error("offline")));
    runInThisContext(SCRIPT);
    await flushPromises();
    expect(own(document.getElementById("skeds"))).toBe("No tests planned.");
    expect(document.querySelector("#sked-past tbody")?.textContent).toBe("No past tests.");
  });

  it("is the page's own section: shown without the script, with the row that says no test is planned, and reached from the menu of every page", () => {
    const page = readFileSync(join(SITE, "index.html"), "utf-8");
    expect(page).toContain('<section class="sec" id="skeds">');
    expect(page).toContain('<tbody><tr><td colspan="3">No tests planned.</td></tr></tbody>');
    expect(page).toContain('<table class="why skeds" id="sked-past">');
    expect(page).toContain('<tbody><tr><td colspan="3">No past tests.</td></tr></tbody>');
    expect(page).toContain('<a href="#skeds">HF tests</a>');
    for (const other of [
      "faq.html",
      "first-test.html",
      "aprs-below-the-noise.html",
      "aprs-over-hf-mercury.html",
      "aprs-over-hf-one-page.html",
    ])
      expect(readFileSync(join(SITE, other), "utf-8"), other).toContain('<a href="./#skeds">HF tests</a>');
  });

  it("drops a row that is not right alone, and writes what is left as text: a call with markup, a time that is no time, a dial of no form, an end before the start", async () => {
    const section = await run({
      v: 1,
      skeds: [
        row("<img src=x onerror=alert(1)>"),
        row("OH2BAD", { from: "tomorrow" }),
        row("OH2BAD", { to: 5 }),
        row("OH2BAD", { dial: "7.0541 MHz <b>USB</b>" }),
        row("OH2BAD", { dial: "145.500 MHz FM" }),
        row("OH2BAD", { from: hours(4), to: hours(2) }),
        row("oh2low"),
        row("OH2TOOLONG"),
        null,
        "OH2STR",
        row("OH2GBA-7"),
      ],
    });
    expect(cells(section)).toEqual([["OH2GBA-7", "Wed 21 Oct 14:00 to 16:00", "7.0541 MHz USB"]]);
    expect(section.querySelector("img, b")).toBeNull();
  });

  it("shows twelve rows at the most", async () => {
    const skeds = Array.from({ length: 30 }, (_, i) =>
      row(`OH2A${String(i).padStart(2, "0")}`, { from: hours(2 + i), to: hours(3 + i) }),
    );
    expect(cells(await run({ v: 1, skeds })).length).toBe(12);
  });

  it("lists the past tests under the board, newest first, from the file beside it and the board's own that have ended, never the note", async () => {
    const section = await run(
      {
        v: 1,
        skeds: [
          row("OH2GBA", { id: "aaaaaaaaaaa1", from: hours(-3), to: hours(-1) }),
          row("OH2XYZ", { id: "aaaaaaaaaaa2", from: hours(-3), to: hours(-1) }),
          row("OH2LAT", { id: "aaaaaaaaaaa3" }),
        ],
      },
      200,
      {
        v: 1,
        past: [
          row("OH3ABC", { id: "bbbbbbbbbbb1", from: hours(-9), to: hours(-8), dial: "14.1070 MHz USB" }),
          row("OH3OLD", { id: "bbbbbbbbbbb2", from: hours(-722), to: hours(-721) }),
          row("<b>x</b>", { id: "bbbbbbbbbbb3", from: hours(-9), to: hours(-8) }),
          row("OH2GBA", { id: "aaaaaaaaaaa1", from: hours(-3), to: hours(-1) }),
        ],
      },
    );
    expect(cells(section)).toEqual([["OH2LAT", "Wed 21 Oct 14:00 to 16:00", "7.0541 MHz USB"]]);
    expect(pastCells(section)).toEqual([
      ["OH2GBA, OH2XYZ", "Wed 21 Oct 09:00 to 11:00", "7.0541 MHz USB"],
      ["OH3ABC", "Wed 21 Oct 03:00 to 04:00", "14.1070 MHz USB"],
    ]);
    expect(section.textContent).not.toContain("Mercury");
    expect(section.querySelector("b")).toBeNull();
  });

  it("shows twenty past tests at the most, and the page's own row when none was read", async () => {
    const past = Array.from({ length: 25 }, (_, i) =>
      row(`OH2A${String(i).padStart(2, "0")}`, {
        id: `cccccccccc${String(i).padStart(2, "0")}`,
        from: hours(-3 - 2 * i),
        to: hours(-2 - 2 * i),
      }),
    );
    expect(pastCells(await run({ v: 1, skeds: [] }, 200, { v: 1, past }))).toHaveLength(20);
    expect(pastCells(await run({ v: 1, skeds: [] }, 200, { v: 1, past }))[0]?.[0]).toBe("OH2A00");
    for (const gone of [undefined, { v: 2, past }, { v: 1, past: "x" }, null, new Error("not json")])
      expect(pastCells(await run({ v: 1, skeds: [] }, 200, gone)), JSON.stringify(gone)).toEqual([["No past tests."]]);
  });

  it("builds the rows with text nodes, not with markup", () => {
    expect(SCRIPT).not.toMatch(/innerHTML|insertAdjacentHTML|outerHTML|document\.write/);
  });
});
