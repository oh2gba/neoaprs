// The suggested frequencies row of the HF radio's box (HfFrequencies.vue): plain-text entries
// one to a line, the room of four lines kept, the list following what the daemon says, and the
// daemon asked to refresh the project's file when the row comes into view, at most once a minute
// from one page.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HfFrequencies from "@/components/HfFrequencies.vue";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { pageRadio } from "@/lib/radios";
import { hfRow } from "@/test/fixtures";

const HERE = dirname(fileURLToPath(import.meta.url));
const asked = (send: { mock: { calls: unknown[][] } }) =>
  send.mock.calls.map(([c]) => c).filter((c) => (c as { cmd: string }).cmd === "frequencies");

/** Radio 2, the Mercury modem, with this list (the fixtures' four where none is given). */
const radioWith = (frequencies?: { band: string; dial: string }[]) =>
  pageRadio(hfRow({}, frequencies === undefined ? {} : { frequencies }));

describe("the suggested frequencies row", () => {
  it("is labelled Suggested frequencies and shows each entry as plain text on a line of its own: the band, then the dial in monospace", () => {
    const daemon = fakeDaemon();
    const wrapper = mount(HfFrequencies, { props: { radio: radioWith() }, global: withDaemon(daemon) });
    expect(wrapper.find("label").text()).toBe("Suggested frequencies");
    const output = wrapper.find("output#hf-frequencies-2");
    expect(output.exists()).toBe(true);
    expect(wrapper.find("input, select, textarea").exists()).toBe(false);
    const lines = output.findAll(".freq");
    expect(lines.map((line) => line.text())).toEqual([
      "80 m 3.5850 MHz USB",
      "40 m 7.0541 MHz USB",
      "20 m 14.1070 MHz USB",
      "6 m 50.6200 MHz USB",
    ]);
    expect(lines.map((line) => line.find(".dial").classes())).toEqual(
      Array.from({ length: 4 }, (): unknown => expect.arrayContaining(["mono"])),
    );
    expect(lines.map((line) => line.find(".band").text())).toEqual(["80 m", "40 m", "20 m", "6 m"]);
  });

  it("follows the list the daemon says: one entry, four, none", async () => {
    const daemon = fakeDaemon();
    const wrapper = mount(HfFrequencies, {
      props: { radio: radioWith([{ band: "30 m", dial: "10.1462 MHz USB" }]) },
      global: withDaemon(daemon),
    });
    expect(wrapper.findAll(".freq").map((line) => line.text())).toEqual(["30 m 10.1462 MHz USB"]);
    await wrapper.setProps({
      radio: radioWith([
        { band: "40 m", dial: "7.0541 MHz USB" },
        { band: "20 m", dial: "14.1070 MHz USB" },
        { band: "17 m", dial: "18.1000 MHz USB" },
        { band: "80 m", dial: "3.5850 MHz USB" },
      ]),
    });
    expect(wrapper.findAll(".freq")).toHaveLength(4);
    await wrapper.setProps({ radio: radioWith([]) });
    expect(wrapper.findAll(".freq")).toHaveLength(0);
    expect(wrapper.find("#hf-frequencies-2").exists()).toBe(true);
  });

  it("keeps the room of four lines, the most the list has, so that nothing moves when it changes", () => {
    const source = readFileSync(join(HERE, "HfFrequencies.vue"), "utf-8");
    expect(source).toMatch(/\.freqs \{[^}]*display: block;[^}]*min-height: 6em;[^}]*line-height: 1\.5;/);
    expect(source).toMatch(/\.freq \{\s*display: block;\s*height: 1\.5em;[^}]*white-space: nowrap;/);
  });
});

describe("asking the daemon to look at the project's file", () => {
  const original = globalThis.IntersectionObserver;
  let callback: ((entries: { isIntersecting: boolean }[]) => void) | null = null;
  let disconnected = 0;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-03T12:00:00Z"));
    callback = null;
    disconnected = 0;
    globalThis.IntersectionObserver = class {
      constructor(run: (entries: { isIntersecting: boolean }[]) => void) {
        callback = run;
      }
      observe(): void {}
      disconnect(): void {
        disconnected++;
      }
    } as unknown as typeof IntersectionObserver;
  });
  afterEach(() => {
    vi.useRealTimers();
    globalThis.IntersectionObserver = original;
  });

  it("asks when the row comes into view, not before, and not more than once a minute", () => {
    const daemon = fakeDaemon();
    mount(HfFrequencies, { props: { radio: radioWith() }, global: withDaemon(daemon) });
    expect(asked(daemon.send)).toEqual([]);
    callback?.([{ isIntersecting: false }]);
    expect(asked(daemon.send)).toEqual([]);
    callback?.([{ isIntersecting: true }]);
    expect(asked(daemon.send)).toEqual([{ cmd: "frequencies" }]);
    vi.advanceTimersByTime(30_000);
    callback?.([{ isIntersecting: true }]);
    expect(asked(daemon.send)).toHaveLength(1);
    vi.advanceTimersByTime(31_000);
    callback?.([{ isIntersecting: true }]);
    expect(asked(daemon.send)).toHaveLength(2);
  });

  it("asks when the socket opens if the row came into view before it was open (a reload with Settings in front), and once", async () => {
    const daemon = fakeDaemon({ connection: "connecting" });
    mount(HfFrequencies, { props: { radio: radioWith() }, global: withDaemon(daemon) });
    callback?.([{ isIntersecting: true }]);
    expect(asked(daemon.send)).toEqual([]);
    await tell(daemon, { connection: "open" });
    expect(asked(daemon.send)).toEqual([{ cmd: "frequencies" }]);
    await tell(daemon, { connection: "closed" });
    await tell(daemon, { connection: "open" });
    expect(asked(daemon.send)).toHaveLength(1);
  });

  it("stops watching when the row goes", () => {
    const daemon = fakeDaemon();
    const wrapper = mount(HfFrequencies, { props: { radio: radioWith() }, global: withDaemon(daemon) });
    wrapper.unmount();
    expect(disconnected).toBe(1);
  });

  it("asks once at once where there is nothing to watch with", () => {
    globalThis.IntersectionObserver = undefined as unknown as typeof IntersectionObserver;
    const daemon = fakeDaemon();
    mount(HfFrequencies, { props: { radio: radioWith() }, global: withDaemon(daemon) });
    expect(asked(daemon.send)).toEqual([{ cmd: "frequencies" }]);
  });
});

// Every radio's box: its own modem's list under an id with the radio's (the list is the station's).
describe("the suggested frequencies of each radio's box", () => {
  it("shows that radio's modem's list under an id of its own", () => {
    const original = globalThis.IntersectionObserver;
    globalThis.IntersectionObserver = undefined as unknown as typeof IntersectionObserver;
    try {
      const daemon = fakeDaemon();
      const radio = pageRadio(hfRow({ id: 6 }, { frequencies: [{ band: "30 m", dial: "10.1462 MHz USB" }] }));
      const wrapper = mount(HfFrequencies, { props: { radio }, global: withDaemon(daemon) });
      expect(wrapper.find("output#hf-frequencies-6").exists()).toBe(true);
      expect(wrapper.find("label").attributes("for")).toBe("hf-frequencies-6");
      expect(wrapper.findAll(".freq").map((line) => line.text())).toEqual(["30 m 10.1462 MHz USB"]);
      expect(daemon.send.mock.calls.map(([c]) => c)).toEqual([{ cmd: "frequencies" }]);
    } finally {
      globalThis.IntersectionObserver = original;
    }
  });
});
