// The suggested frequencies row of the HF radio's box (HfFrequencies.vue): one row whose button
// opens the list in a dialog, one entry to a line, the room of five lines kept, the list following
// what the daemon says, and the daemon asked to refresh the project's file when the row comes into
// view (at most once a minute from one page) and when the dialog opens.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HfFrequencies from "@/components/HfFrequencies.vue";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { pageRadio } from "@/lib/radios";
import { hfRow } from "@/test/fixtures";

const HERE = dirname(fileURLToPath(import.meta.url));
const asked = (send: { mock: { calls: unknown[][] } }) =>
  send.mock.calls.map(([c]) => c).filter((c) => (c as { cmd: string }).cmd === "frequencies");

/** Radio 2, the Mercury modem, with this list (the fixtures' five where none is given). */
const radioWith = (frequencies?: { band: string; dial: string }[]) =>
  pageRadio(hfRow({}, frequencies === undefined ? {} : { frequencies }));

const dialog = () => document.querySelector<HTMLElement>("[role='dialog']");
const shown = () => [...(dialog()?.querySelectorAll(".freq") ?? [])].map((line) => line.textContent?.trim());
afterEach(() => {
  document.body.innerHTML = "";
});

describe("the suggested frequencies row", () => {
  it("is one row labelled Suggested frequencies whose button, Show, opens them in a dialog with one line that says what they are", async () => {
    const daemon = fakeDaemon();
    const wrapper = mount(HfFrequencies, {
      props: { radio: radioWith() },
      global: withDaemon(daemon),
      attachTo: document.body,
    });
    expect(wrapper.find("label").text()).toBe("Suggested frequencies");
    const button = wrapper.find("button#hf-frequencies-2");
    expect(wrapper.find("label").attributes("for")).toBe("hf-frequencies-2");
    expect(button.text()).toBe("Show");
    expect(button.classes()).toContain("btn");
    expect(dialog()).toBeNull();
    await button.trigger("click");
    const title = document.getElementById(dialog()?.getAttribute("aria-labelledby") ?? "");
    expect(title?.textContent).toBe("Suggested frequencies");
    expect([...(dialog()?.querySelectorAll("p") ?? [])].map((p) => p.textContent)).toEqual([
      "Frequencies the project suggests for APRS over Mercury. Tune the radio to one, upper sideband (USB).",
    ]);
    expect(shown()).toEqual([
      "80 m 3.5850 MHz USB",
      "40 m 7.0541 MHz USB",
      "20 m 14.1070 MHz USB",
      "10 m 28.1800 MHz USB",
      "6 m 50.6200 MHz USB",
    ]);
    expect([...(dialog()?.querySelectorAll(".freq .dial") ?? [])].every((d) => d.classList.contains("mono"))).toBe(
      true,
    );
    dialog()?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await flushPromises();
    expect(dialog()).toBeNull();
    expect(document.activeElement).toBe(button.element);
    wrapper.unmount();
  });

  it("follows the list the daemon says while the dialog is open: one entry, five, none", async () => {
    const daemon = fakeDaemon();
    const wrapper = mount(HfFrequencies, {
      props: { radio: radioWith([{ band: "30 m", dial: "10.1462 MHz USB" }]) },
      global: withDaemon(daemon),
    });
    await wrapper.find("button").trigger("click");
    expect(shown()).toEqual(["30 m 10.1462 MHz USB"]);
    await wrapper.setProps({
      radio: radioWith([
        { band: "40 m", dial: "7.0541 MHz USB" },
        { band: "20 m", dial: "14.1070 MHz USB" },
        { band: "17 m", dial: "18.1000 MHz USB" },
        { band: "10 m", dial: "28.1800 MHz USB" },
        { band: "80 m", dial: "3.5850 MHz USB" },
      ]),
    });
    expect(shown()).toHaveLength(5);
    await wrapper.setProps({ radio: radioWith([]) });
    expect(shown()).toHaveLength(0);
    wrapper.unmount();
  });

  it("keeps the room of five lines in the dialog, the most the list has, so that it keeps its size when the list comes", () => {
    const source = readFileSync(join(HERE, "HfFrequencies.vue"), "utf-8");
    expect(source).toMatch(/\.freqs \{[^}]*min-height: 7\.5em;[^}]*line-height: 1\.5;/);
    expect(source).toMatch(/\.freq \{\s*height: 1\.5em;[^}]*white-space: nowrap;/);
  });

  it("asks the daemon for the list again when the dialog opens", async () => {
    const original = globalThis.IntersectionObserver;
    globalThis.IntersectionObserver = class {
      observe(): void {}
      disconnect(): void {}
    } as unknown as typeof IntersectionObserver;
    try {
      const daemon = fakeDaemon();
      const wrapper = mount(HfFrequencies, { props: { radio: radioWith() }, global: withDaemon(daemon) });
      expect(asked(daemon.send)).toEqual([]);
      await wrapper.find("button").trigger("click");
      expect(asked(daemon.send)).toEqual([{ cmd: "frequencies" }]);
      wrapper.unmount();
    } finally {
      globalThis.IntersectionObserver = original;
    }
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
  it("shows that radio's modem's list under an id of its own", async () => {
    const original = globalThis.IntersectionObserver;
    globalThis.IntersectionObserver = undefined as unknown as typeof IntersectionObserver;
    try {
      const daemon = fakeDaemon();
      const radio = pageRadio(hfRow({ id: 6 }, { frequencies: [{ band: "30 m", dial: "10.1462 MHz USB" }] }));
      const wrapper = mount(HfFrequencies, { props: { radio }, global: withDaemon(daemon) });
      expect(wrapper.find("button#hf-frequencies-6").exists()).toBe(true);
      expect(wrapper.find("label").attributes("for")).toBe("hf-frequencies-6");
      expect(daemon.send.mock.calls.map(([c]) => c)).toEqual([{ cmd: "frequencies" }]);
      await wrapper.find("button").trigger("click");
      expect(shown()).toEqual(["30 m 10.1462 MHz USB"]);
      wrapper.unmount();
    } finally {
      globalThis.IntersectionObserver = original;
    }
  });
});
