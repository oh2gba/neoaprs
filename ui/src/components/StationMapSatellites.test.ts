import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { forgetLayerTicks } from "@/composables/useMapLayers";
import { FRAME_MS } from "@/composables/useMapMotion";
import type { SatelliteFeatures } from "@/lib/layers/satellite";
import { FakeMap, resetFakes } from "@/test/fakemap";
import { tell } from "@/test/context";
import { mountStationMap } from "@/test/stationmap";
import { mapState, station, table } from "@/test/fixtures";
import { DURING, satelliteCard, satellitesMessage } from "@/test/satellitefixtures";

const last = <T>(source: string): T | undefined =>
  FakeMap.last().getSource(source)?.setData.mock.calls.at(-1)?.[0] as T | undefined;

beforeEach(() => {
  resetFakes();
  localStorage.clear();
  forgetLayerTicks();
});
afterEach(() => {
  vi.useRealTimers();
  document.body.replaceChildren();
});

describe("the satellites on the map", () => {
  it("draw an open card's track and footprint from where its mark is, at each step of the motion", async () => {
    vi.useFakeTimers({ now: DURING });
    localStorage.setItem("NeoAPRS.layer.satellites", "on");
    const made = mountStationMap({
      stations: table(station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94 })),
      selected: null,
      focus: null,
      home: { lat: 60.17, lon: 24.94 },
      now: DURING,
      dark: false,
      aging: { defaultMin: 0 },
    });
    await flushPromises();
    FakeMap.last().fire("style.load");
    await tell(made.daemon, { map: mapState() });
    made.daemon.satellites.open(25544);
    made.daemon.satelliteStore.handlers.satellites(satellitesMessage({ cards: [satelliteCard()] }));
    await nextTick();
    for (const ms of [3 * FRAME_MS, 7 * FRAME_MS]) {
      vi.advanceTimersByTime(ms);
      const mark = last<SatelliteFeatures["marks"]>("satellites")?.features[0].geometry.coordinates;
      const track = last<SatelliteFeatures["tracks"]>("satellite-tracks")?.features[0].geometry.coordinates[0][0];
      expect(mark).toBeDefined();
      expect(track).toEqual(mark);
    }
  });

  it("does not hop when a new message's points put the mark a little off the last ones'", async () => {
    vi.useFakeTimers({ now: DURING });
    localStorage.setItem("NeoAPRS.layer.satellites", "on");
    const made = mountStationMap({
      stations: table(station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94 })),
      selected: null,
      focus: null,
      home: { lat: 60.17, lon: 24.94 },
      now: DURING,
      dark: false,
      aging: { defaultMin: 0 },
    });
    await flushPromises();
    FakeMap.last().fire("style.load");
    await tell(made.daemon, { map: mapState() });
    made.daemon.satelliteStore.handlers.satellites(satellitesMessage());
    await nextTick();
    vi.advanceTimersByTime(3 * FRAME_MS);
    const mark = () => last<SatelliteFeatures["marks"]>("satellites")?.features[0].geometry.coordinates ?? [0, 0];
    const before = mark();
    const off = satellitesMessage({
      at: new Date(Date.now()).toISOString(),
      satellites: satellitesMessage().satellites.map((one) => ({
        ...one,
        points: one.points.map((point) => ({ ...point, lat: point.lat + 0.006 })),
      })),
    });
    made.daemon.satelliteStore.handlers.satellites(off);
    await nextTick();
    expect(Math.abs(mark()[1] - before[1])).toBeLessThan(0.001);
  });
});
