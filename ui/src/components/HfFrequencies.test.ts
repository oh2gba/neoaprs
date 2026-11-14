// The suggested frequencies row of the HF radio's box (HfFrequencies.vue, composables/useWhenShown.ts): the label says "suggested", the entries are plain text one to a line, band then the dial in the monospace font, the room of four lines is kept,
// the list follows what the daemon says, and the daemon is asked to look at the project's file when the row comes into view, at most once a minute from one page.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HfFrequencies from "@/components/HfFrequencies.vue";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { hfState } from "@/test/fixtures";

const HERE = dirname(fileURLToPath(import.meta.url));
const asked = (send: { mock: { calls: unknown[][] } }) => send.mock.calls.map(([c]) => c).filter((c) => (c as { cmd: string }).cmd === "hf_frequencies");

function withModem(frequencies: { band: string; dial: string }[]) {
  const state = hfState();
  return { ...state, modem: { ...state.modem!, frequencies } };
}

describe("the suggested frequencies row", () => {
  it("is labelled Suggested frequencies and shows each entry as plain text on a line of its own: the band, then the dial in monospace", () => {
    const daemon = fakeDaemon({ hf: hfState() });
    const wrapper = mount(HfFrequencies, { global: withDaemon(daemon) });
    expect(wrapper.find("label").text()).toBe("Suggested frequencies");
    const output = wrapper.find("output#hf-frequencies");
    expect(output.exists()).toBe(true);
    expect(wrapper.find("input, select, textarea").exists()).toBe(false);
    const lines = output.findAll(".freq");
    expect(lines.map((line) => line.text())).toEqual(["40 m 7.0541 MHz USB", "20 m 14.1070 MHz USB"]);
    expect(lines.map((line) => line.find(".dial").classes())).toEqual([expect.arrayContaining(["mono"]), expect.arrayContaining(["mono"])]);
    expect(lines.map((line) => line.find(".band").text())).toEqual(["40 m", "20 m"]);
  });

  it("follows the list the daemon says: one entry, four, none", async () => {
    const daemon = fakeDaemon({ hf: withModem([{ band: "30 m", dial: "10.1462 MHz USB" }]) });
    const wrapper = mount(HfFrequencies, { global: withDaemon(daemon) });
    expect(wrapper.findAll(".freq").map((line) => line.text())).toEqual(["30 m 10.1462 MHz USB"]);
    await tell(daemon, {
      hf: withModem([
        { band: "40 m", dial: "7.0541 MHz USB" },
        { band: "20 m", dial: "14.1070 MHz USB" },
        { band: "17 m", dial: "18.1000 MHz USB" },
        { band: "80 m", dial: "3.5850 MHz USB" },
      ]),
    });
    expect(wrapper.findAll(".freq")).toHaveLength(4);
    await tell(daemon, { hf: withModem([]) });
    expect(wrapper.findAll(".freq")).toHaveLength(0);
    expect(wrapper.find("#hf-frequencies").exists()).toBe(true);
  });

  it("keeps the room of four lines, the most the list has, so that nothing moves when it changes", () => {
    const source = readFileSync(join(HERE, "HfFrequencies.vue"), "utf-8");
    expect(source).toMatch(/\.freqs \{[^}]*display: block;[^}]*min-height: 6em;[^}]*line-height: 1\.5;/);
    expect(source).toMatch(/\.freq \{\s*display: block;/);
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
    const daemon = fakeDaemon({ hf: hfState() });
    mount(HfFrequencies, { global: withDaemon(daemon) });
    expect(asked(daemon.send)).toEqual([]);
    callback?.([{ isIntersecting: false }]);
    expect(asked(daemon.send)).toEqual([]);
    callback?.([{ isIntersecting: true }]);
    expect(asked(daemon.send)).toEqual([{ cmd: "hf_frequencies" }]);
    vi.advanceTimersByTime(30_000);
    callback?.([{ isIntersecting: true }]);
    expect(asked(daemon.send)).toHaveLength(1);
    vi.advanceTimersByTime(31_000);
    callback?.([{ isIntersecting: true }]);
    expect(asked(daemon.send)).toHaveLength(2);
  });

  it("stops watching when the row goes", () => {
    const daemon = fakeDaemon({ hf: hfState() });
    const wrapper = mount(HfFrequencies, { global: withDaemon(daemon) });
    wrapper.unmount();
    expect(disconnected).toBe(1);
  });

  it("asks once at once where there is nothing to watch with", () => {
    globalThis.IntersectionObserver = undefined as unknown as typeof IntersectionObserver;
    const daemon = fakeDaemon({ hf: hfState() });
    mount(HfFrequencies, { global: withDaemon(daemon) });
    expect(asked(daemon.send)).toEqual([{ cmd: "hf_frequencies" }]);
  });
});
