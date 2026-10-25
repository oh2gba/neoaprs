import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { FakeMap, resetFakes } from "@/test/fakemap";
import { mountStationMap } from "@/test/stationmap";
import { NOW, gpsOff, gpsState, station, table } from "@/test/fixtures";

const props = (gps: ReturnType<typeof gpsState>) => ({
  stations: table(station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94, symbol_code: ">" })),
  selected: null,
  focus: null,
  home: { lat: 60.17, lon: 24.94 },
  now: NOW,
  dark: false,
  aging: { defaultMin: 0 },
  gps,
});

async function mounted(gps = gpsState({ mobile: true })) {
  const mounted = mountStationMap(props(gps));
  await flushPromises();
  return mounted;
}
const button = (wrapper: Awaited<ReturnType<typeof mounted>>["wrapper"]) => wrapper.find<HTMLButtonElement>("button.followme");

beforeEach(() => {
  resetFakes();
  localStorage.clear();
});
afterEach(() => document.body.replaceChildren());

describe("Follow me on the map", () => {
  it("is offered while the beacon is mobile and the GPS has a fix, and not otherwise", async () => {
    const { wrapper, daemon } = await mounted();
    expect(button(wrapper).text()).toBe("Follow me");
    expect(button(wrapper).attributes("aria-pressed")).toBe("false");
    daemon.gps.value = gpsState({ mobile: false });
    await flushPromises();
    expect(button(wrapper).exists()).toBe(false);
    daemon.gps.value = gpsState({ mobile: true, state: "no_fix", lat: null, lon: null });
    await flushPromises();
    expect(button(wrapper).exists()).toBe(false);
    daemon.gps.value = gpsOff();
    await flushPromises();
    expect(button(wrapper).exists()).toBe(false);
  });

  it("is not there before the daemon has told the GPS", async () => {
    const { wrapper, daemon } = await mounted();
    daemon.gps.value = null;
    await flushPromises();
    expect(button(wrapper).exists()).toBe(false);
  });

  it("does nothing to the map until it is pressed", async () => {
    const { daemon } = await mounted();
    daemon.gps.value = gpsState({ mobile: true, lat: 60.5, lon: 24.5 });
    await flushPromises();
    expect(FakeMap.last().eases).toEqual([]);
  });

  it("eases the map to the fix when it is pressed, and to each new place of it, not to the same place again", async () => {
    const { wrapper, daemon } = await mounted();
    await button(wrapper).trigger("click");
    await flushPromises();
    expect(button(wrapper).attributes("aria-pressed")).toBe("true");
    expect(FakeMap.last().eases).toEqual([{ center: [24.1452, 60.4295], zoom: 14, duration: 800 }]);
    daemon.gps.value = gpsState({ mobile: true });
    await flushPromises();
    expect(FakeMap.last().eases).toHaveLength(1);
    daemon.gps.value = gpsState({ mobile: true, lat: 60.43, lon: 24.15 });
    await flushPromises();
    expect(FakeMap.last().eases.at(-1)).toMatchObject({ center: [24.15, 60.43] });
  });

  it("keeps the zoom the person has when it is closer than the following zoom", async () => {
    const { wrapper } = await mounted();
    FakeMap.last().zoom = 16;
    await button(wrapper).trigger("click");
    await flushPromises();
    expect(FakeMap.last().eases).toEqual([{ center: [24.1452, 60.4295], zoom: 16, duration: 800 }]);
  });

  it("lets go when the person drags the map, and again when the button is pressed", async () => {
    const { wrapper, daemon } = await mounted();
    await button(wrapper).trigger("click");
    await flushPromises();
    FakeMap.last().fire("dragstart");
    await flushPromises();
    expect(button(wrapper).attributes("aria-pressed")).toBe("false");
    daemon.gps.value = gpsState({ mobile: true, lat: 60.5, lon: 24.5 });
    await flushPromises();
    expect(FakeMap.last().eases).toHaveLength(1);
    await button(wrapper).trigger("click");
    await flushPromises();
    expect(FakeMap.last().eases.at(-1)).toMatchObject({ center: [24.5, 60.5] });
  });

  it("lets go when the fix is lost or the beacon is no longer mobile, and does not take hold again by itself", async () => {
    const { wrapper, daemon } = await mounted();
    await button(wrapper).trigger("click");
    await flushPromises();
    daemon.gps.value = gpsState({ mobile: true, state: "stale" });
    await flushPromises();
    daemon.gps.value = gpsState({ mobile: true, lat: 60.5, lon: 24.5 });
    await flushPromises();
    expect(button(wrapper).attributes("aria-pressed")).toBe("false");
    expect(FakeMap.last().eases).toHaveLength(1);
  });
});
