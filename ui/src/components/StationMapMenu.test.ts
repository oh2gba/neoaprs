import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { shallowRef } from "vue";
import { useScopeLooks } from "@/composables/useScopeLooks";
import type { RadioRow } from "@/protocol/protocol";
import { FakeMap, resetFakes } from "@/test/fakemap";
import { mountStationMap } from "@/test/stationmap";
import { cssRule } from "@/test/css";
import { NOW, modemState, radioRow, radiosTopic, station, table } from "@/test/fixtures";
import { tell, type FakeDaemon } from "@/test/context";

const props = () => ({
  stations: table(station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94 })),
  selected: null,
  focus: null,
  home: { lat: 60.17, lon: 24.94 },
  now: NOW,
  dark: false,
  aging: { defaultMin: 0 },
});

const menu = () => document.querySelector<HTMLElement>("[role='menu'].mapmenu");
const items = () => [...document.querySelectorAll<HTMLElement>(".mapmenu [role='menuitem']")];
const item = (name: string) => document.querySelector<HTMLElement>(`.mapmenu [role='menuitem'][data-item='${name}']`);

/** The map's own contextmenu event, as MapLibre fires it for a right-click at a place. */
function rightClick(lat: number, lng: number, clientX = 300, clientY = 200) {
  const originalEvent = new MouseEvent("contextmenu", { clientX, clientY, cancelable: true });
  const preventDefault = vi.fn();
  FakeMap.last().fire("contextmenu", { lngLat: { lat, lng }, point: { x: 100, y: 50 }, originalEvent, preventDefault });
  return { originalEvent, preventDefault };
}

async function mounted() {
  const { wrapper, daemon } = mountStationMap(props());
  await flushPromises();
  return { wrapper, daemon };
}

beforeEach(() => {
  resetFakes();
  localStorage.clear();
});
afterEach(() => document.body.replaceChildren());

describe("the menu of the map", () => {
  it("opens on a right-click where the pointer is, with the place to copy, the locator, then Statistics, Packets and Replay (no Monitor without a scope)", async () => {
    await mounted();
    const { originalEvent, preventDefault } = rightClick(60.17345, 24.94123);
    await flushPromises();
    expect(preventDefault).toHaveBeenCalled();
    expect(originalEvent.defaultPrevented).toBe(true);
    expect(menu()).not.toBeNull();
    expect(items().map((b) => b.dataset.item)).toEqual(["position", "locator", "stats", "packets", "replay"]);
    expect(items().map((b) => b.textContent?.trim())).toEqual([
      "Copy position 60.17345, 24.94123",
      "Copy locator KP20le",
      "Statistics",
      "Packets",
      "Replay",
    ]);
    expect(menu()?.style.left).toBe("300px");
    expect(menu()?.style.top).toBe("200px");
    expect(document.activeElement).toBe(item("position"));
  });

  it("has Monitor between Packets and Replay while the Mercury radio has a scope, and says so to the page when it is chosen", async () => {
    const { wrapper, daemon } = await mounted();
    const modem = modemState({ scope: true });
    await tell(daemon, {
      radios: radiosTopic(
        radioRow(1, "kenwood-tnc2", { enabled: false, state: "stopped" }),
        radioRow(2, "mercury", { modem }),
      ),
    });
    rightClick(60.17345, 24.94123);
    await flushPromises();
    expect(items().map((b) => b.dataset.item)).toEqual([
      "position",
      "locator",
      "stats",
      "packets",
      "monitor",
      "replay",
    ]);
    expect(item("monitor")?.textContent?.trim()).toBe("Monitor");
    item("monitor")?.click();
    await flushPromises();
    expect(wrapper.emitted("card")).toEqual([["monitor"]]);
    expect(menu()).toBeNull();
  });

  it("copies the place as decimal degrees and says so; the locator too", async () => {
    const { daemon } = await mounted();
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    rightClick(60.17345, 24.94123);
    await flushPromises();
    item("position")?.click();
    await flushPromises();
    expect(writeText).toHaveBeenCalledWith("60.17345, 24.94123");
    expect(daemon.say).toHaveBeenCalledWith("Copied 60.17345, 24.94123");
    expect(menu()).toBeNull();
    rightClick(60.17345, 24.94123);
    await flushPromises();
    item("locator")?.click();
    await flushPromises();
    expect(writeText).toHaveBeenLastCalledWith("KP20le");
    vi.unstubAllGlobals();
  });

  it("asks the page for the statistics card and for the Packets card, and closes", async () => {
    const { wrapper } = await mounted();
    rightClick(60.1, 24.9);
    await flushPromises();
    item("stats")?.click();
    await flushPromises();
    expect(wrapper.emitted("card")).toEqual([["stats"]]);
    expect(menu()).toBeNull();
    rightClick(60.1, 24.9);
    await flushPromises();
    item("packets")?.click();
    await flushPromises();
    expect(wrapper.emitted("card")).toEqual([["stats"], ["packets"]]);
    expect(wrapper.emitted("select")).toBeUndefined(); // (the cards stay)
  });

  it("closes with Esc, and does not open without a place", async () => {
    await mounted();
    rightClick(60.1, 24.9);
    await flushPromises();
    menu()?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await flushPromises();
    expect(menu()).toBeNull();
    FakeMap.last().fire("contextmenu", {});
    await flushPromises();
    expect(menu()).toBeNull();
  });

  it("opens on a finger held on the map, for the place under it", async () => {
    vi.useFakeTimers();
    const { wrapper } = await mounted();
    FakeMap.last().place = { lng: 24.5, lat: 60.5 };
    const root = wrapper.find(".stationmap").element;
    const down = new Event("pointerdown", { bubbles: true }) as PointerEvent;
    Object.defineProperties(down, {
      pointerType: { value: "touch" },
      isPrimary: { value: true },
      clientX: { value: 120 },
      clientY: { value: 80 },
    });
    root.dispatchEvent(down);
    vi.advanceTimersByTime(600);
    await flushPromises();
    expect(menu()).not.toBeNull();
    expect(item("position")?.textContent?.trim()).toBe("Copy position 60.50000, 24.50000");
    vi.useRealTimers();
  });
});

/** A Mercury radio whose modem has the interface (or has not, `scope` false). */
const mercury = (id: number, extra: Partial<RadioRow> = {}, scope = true): RadioRow =>
  radioRow(id, "mercury", { modem: modemState({ scope }), ...extra });

/**
 * The map with these radios told, and the page's counting of who looks given the topic `radios` as
 * the page makes it.
 */
async function withRadios(
  ...rows: RadioRow[]
): Promise<{ wrapper: Awaited<ReturnType<typeof mounted>>["wrapper"]; daemon: FakeDaemon }> {
  const { wrapper, daemon } = await mounted();
  await tell(daemon, { radios: radiosTopic(...rows) });
  daemon.scope = useScopeLooks(daemon.send, daemon.connection, shallowRef(true), { radios: daemon.radios });
  return { wrapper, daemon };
}
const monitors = () => items().filter((b) => b.dataset.item === "monitor");

describe("the menu's Monitor by radio", () => {
  it("has one Monitor for each radio that has a scope now, in the order of their boxes, each named where several radios are on, and none for a radio off or without one", async () => {
    await withRadios(
      radioRow(1, "kenwood-tnc2"),
      mercury(4, { name: "40 m", position: 4 }),
      mercury(3, { name: "20 m", position: 3 }),
      mercury(6, { name: "80 m", enabled: false, state: "stopped" }),
      mercury(7, { name: "30 m" }, false),
      radioRow(8, "dummy-hf", { name: "Test" }),
    );
    rightClick(60.17345, 24.94123);
    await flushPromises();
    expect(items().map((b) => b.dataset.item)).toEqual([
      "position",
      "locator",
      "stats",
      "packets",
      "monitor",
      "monitor",
      "replay",
    ]);
    expect(monitors().map((b) => [b.dataset.radio, b.textContent?.trim()])).toEqual([
      ["3", "20 m: Monitor"],
      ["4", "40 m: Monitor"],
    ]);
  });

  it("names the Mercury radio on a station with an Packet and a Mercury radio, and says Monitor alone with one radio on", async () => {
    await withRadios(radioRow(1, "kenwood-tnc2"), mercury(2));
    rightClick(60.1, 24.9);
    await flushPromises();
    expect(monitors().map((b) => b.textContent?.trim())).toEqual(["Mercury: Monitor"]);
    document.body.replaceChildren();
    resetFakes();
    await withRadios(radioRow(1, "kenwood-tnc2", { enabled: false, state: "stopped" }), mercury(2));
    rightClick(60.1, 24.9);
    await flushPromises();
    expect(monitors().map((b) => b.textContent?.trim())).toEqual(["Monitor"]);
  });

  it("puts the card on the radio chosen and says so to the page, and the arrow keys go through every Monitor", async () => {
    const { wrapper, daemon } = await withRadios(mercury(2, { name: "20 m" }), mercury(5, { name: "40 m" }));
    rightClick(60.1, 24.9);
    await flushPromises();
    const list = menu()!;
    const key = (k: string) => list.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true }));
    key("End");
    expect(document.activeElement).toBe(item("replay"));
    key("ArrowUp");
    expect(document.activeElement).toBe(monitors()[1]);
    key("ArrowUp");
    expect(document.activeElement).toBe(monitors()[0]);
    key("ArrowUp");
    expect(document.activeElement).toBe(item("packets"));
    key("ArrowUp");
    expect(document.activeElement).toBe(item("stats"));
    monitors()[1]?.click();
    await flushPromises();
    expect(daemon.scope.monitor.value).toBe(5);
    expect(wrapper.emitted("card")).toEqual([["monitor"]]);
    expect(menu()).toBeNull();
  });

  it("lists six radios' Monitors with names of eight characters whole at 375 px: the menu is kept in the window, its items wrap rather than cut, and it scrolls rather than run off", async () => {
    const names = ["WWWWWWWW", "MMMMMMMM", "Shack 20", "Mast 40m", "Mobile 2", "Base HF3"];
    await withRadios(...names.map((name, i) => mercury(i + 1, { name, number: i + 1 })));
    rightClick(60.1, 24.9, 360, 700);
    await flushPromises();
    expect(monitors().map((b) => b.textContent?.trim())).toEqual(names.map((name) => `${name}: Monitor`));
    expect(cssRule(".ctxmenu")).toMatch(/max-width:\s*calc\(100vw - 16px\)/);
    expect(cssRule(".ctxmenu")).toMatch(/max-height:\s*calc\(100vh - 16px\)/);
    expect(cssRule(".ctxmenu")).toMatch(/overflow-y:\s*auto/);
    expect(cssRule(".ctxmenu-item")).not.toMatch(/white-space:\s*nowrap|text-overflow|overflow:\s*hidden/);
  });
});
