// The ships and the aircraft on the map (composables/useTrafficMap.ts, lib/trafficlayers.ts): their layers made with the style, what they draw following the topics, a click on one opening its card, and the card going when
// the ship leaves the feed.
import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import { FakeMap, resetFakes } from "@/test/fakemap";
import { mountStationMap } from "@/test/stationmap";
import { NOW, aircraftRow, ship, table } from "@/test/fixtures";
import type { AircraftRow, ShipRow } from "@/protocol/protocol";

type Drawn = { features: { properties: { key: string; icon: string; label: string; picked: number } }[] };
const drawn = (source: string) => FakeMap.last().getSource(source)?.setData.mock.calls.at(-1)?.[0] as Drawn | undefined;

beforeEach(() => {
  resetFakes();
  localStorage.clear();
});

async function mounted() {
  const { wrapper, daemon } = mountStationMap({
    stations: table(),
    selected: null,
    focus: null,
    home: { lat: 60.17, lon: 24.94 },
    now: NOW,
    dark: false,
    aging: { defaultMin: 180 },
  });
  const ships = daemon.ships as Map<string, ShipRow>;
  const aircraft = daemon.aircraft as Map<string, AircraftRow>;
  ships.set("230145760", ship());
  aircraft.set("461fa7", aircraftRow());
  await flushPromises();
  return { wrapper, ships, aircraft };
}

describe("the ships and the aircraft on the map", () => {
  it("have layers of their own, drawn from the topics, and a click opens the card of the one clicked", async () => {
    const { wrapper, ships } = await mounted();
    FakeMap.last().fire("style.load");
    expect(FakeMap.last().layers).toEqual(expect.arrayContaining(["traffic-ships", "traffic-aircraft", "traffic-ships-picked", "traffic-aircraft-picked"]));
    ships.set("230000001", ship({ mmsi: 230000001, name: "VIKING GRACE", category: "passenger" }));
    await nextTick();
    expect(drawn("traffic-ships")?.features.map((f) => f.properties.label)).toEqual(["DUNKER", "VIKING GRACE"]);
    expect(drawn("traffic-aircraft")?.features.map((f) => f.properties.icon)).toEqual(["aircraft-jet"]);
    FakeMap.last().fire("click", { features: [{ properties: { key: "230000001" } }] }, "traffic-ships");
    await nextTick();
    expect(wrapper.get(".trafficcard .card-call").text()).toBe("Ship VIKING GRACE");
    expect(drawn("traffic-ships")?.features.find((f) => f.properties.picked === 1)?.properties.key).toBe("230000001");
    ships.delete("230000001");
    await nextTick();
    await nextTick();
    expect(wrapper.find(".trafficcard").exists()).toBe(false);
  });
});
