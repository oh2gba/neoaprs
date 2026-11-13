// The project page's script (site/site.js) as far as it shows the sked board: the section under the HF band is hidden in the page and shown only when a sked to come was read, with the call, the time and the dial and never the note, every
// value written as text. The script is run on a made-up page with a fetch of its own.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { runInThisContext } from "node:vm";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { NOW } from "@/test/fixtures";

const SCRIPT = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "..", "site", "site.js"), "utf-8");
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

async function run(body: unknown, status = 200): Promise<HTMLElement> {
  document.body.innerHTML = `<section id="skeds" hidden><table><tbody><tr><td>placeholder</td></tr></tbody></table></section>`;
  const asked: string[] = [];
  vi.stubGlobal("fetch", (url: string) => {
    asked.push(url);
    return Promise.resolve({ ok: status === 200, json: () => (body instanceof Error ? Promise.reject(body) : Promise.resolve(body)) });
  });
  runInThisContext(SCRIPT);
  await flushPromises();
  expect(asked).toContain("skeds.json");
  const section = document.getElementById("skeds");
  if (section === null) throw new Error("no section");
  return section;
}
const cells = (section: HTMLElement) => [...section.querySelectorAll("tbody tr")].map((tr) => [...tr.children].map((c) => c.textContent));

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
    const section = await run({ v: 1, skeds: [row("OH2LAT", { from: hours(30), to: hours(31), dial: "14.1070 MHz USB" }), row("OH2GBA")] });
    expect(section.hidden).toBe(false);
    expect(cells(section)).toEqual([
      ["OH2GBA", "Wed 21 Oct 14:00 to 16:00", "7.0541 MHz USB"],
      ["OH2LAT", "Thu 22 Oct 18:00 to 19:00", "14.1070 MHz USB"],
    ]);
    expect(section.textContent).not.toContain("Mercury");
  });

  it("writes the end with its day when the sked runs into the next one", async () => {
    const section = await run({ v: 1, skeds: [row("OH2GBA", { from: "2026-10-21T22:00:00Z", to: "2026-10-22T02:00:00Z" })] });
    expect(cells(section)).toEqual([["OH2GBA", "Wed 21 Oct 22:00 to Thu 22 Oct 02:00", "7.0541 MHz USB"]]);
  });

  it("makes skeds with the same times and dial one row that lists the calls", async () => {
    const section = await run({ v: 1, skeds: [row("OH2AAA"), row("OH2BBB"), row("OH2AAA")] });
    expect(cells(section)).toEqual([["OH2AAA, OH2BBB", "Wed 21 Oct 14:00 to 16:00", "7.0541 MHz USB"]]);
  });

  it("stays hidden, with the page's own table, when no sked to come was read", async () => {
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
      expect(section.hidden, JSON.stringify(body)).toBe(true);
      expect(section.querySelector("tbody")?.textContent).toBe("placeholder");
    }
  });

  it("stays hidden when the file cannot be read: not found, not JSON, no network", async () => {
    expect((await run({ v: 1, skeds: [row("OH2GBA")] }, 404)).hidden).toBe(true);
    expect((await run(new Error("not json"))).hidden).toBe(true);
    document.body.innerHTML = `<section id="skeds" hidden><table><tbody></tbody></table></section>`;
    vi.stubGlobal("fetch", () => Promise.reject(new Error("offline")));
    runInThisContext(SCRIPT);
    await flushPromises();
    expect(document.getElementById("skeds")?.hidden).toBe(true);
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
    const skeds = Array.from({ length: 30 }, (_, i) => row(`OH2A${String(i).padStart(2, "0")}`, { from: hours(2 + i), to: hours(3 + i) }));
    expect(cells(await run({ v: 1, skeds })).length).toBe(12);
  });

  it("builds the rows with text nodes, not with markup", () => {
    expect(SCRIPT).not.toMatch(/innerHTML|insertAdjacentHTML|outerHTML|document\.write/);
  });
});
