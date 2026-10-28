import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeMap, resetFakes } from "@/test/fakemap";
import { mountStationMap } from "@/test/stationmap";
import { NOW, station, table } from "@/test/fixtures";

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
  it("opens on a right-click where the pointer is, with the place to copy, the locator, and Statistics last", async () => {
    await mounted();
    const { originalEvent, preventDefault } = rightClick(60.17345, 24.94123);
    await flushPromises();
    expect(preventDefault).toHaveBeenCalled();
    expect(originalEvent.defaultPrevented).toBe(true);
    expect(menu()).not.toBeNull();
    expect(items().map((b) => b.dataset.item)).toEqual(["position", "locator", "stats"]);
    expect(items().map((b) => b.textContent?.trim())).toEqual(["Copy position 60.17345, 24.94123", "Copy locator KP20le", "Statistics"]);
    expect(menu()?.style.left).toBe("300px");
    expect(menu()?.style.top).toBe("200px");
    expect(document.activeElement).toBe(item("position"));
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

  it("asks the page for the statistics card with its last item, and closes", async () => {
    const { wrapper } = await mounted();
    rightClick(60.1, 24.9);
    await flushPromises();
    item("stats")?.click();
    await flushPromises();
    expect(wrapper.emitted("stats")).toEqual([[]]);
    expect(menu()).toBeNull();
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
    Object.defineProperties(down, { pointerType: { value: "touch" }, isPrimary: { value: true }, clientX: { value: 120 }, clientY: { value: 80 } });
    root.dispatchEvent(down);
    vi.advanceTimersByTime(600);
    await flushPromises();
    expect(menu()).not.toBeNull();
    expect(item("position")?.textContent?.trim()).toBe("Copy position 60.50000, 24.50000");
    vi.useRealTimers();
  });
});
