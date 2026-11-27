import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { nextTick } from "vue";
import StationCards from "@/components/StationCards.vue";
import { forgetLayerTicks } from "@/composables/useMapLayers";
import type { SizeClass } from "@/lib/layout";
import { fakeDaemon, withDaemon } from "@/test/context";
import { NOW, ago, station } from "@/test/fixtures";
import { satelliteCard, satellitesMessage } from "@/test/satellitefixtures";

const car = station("OH2ZMA-9", { lat: 60.1, lon: 24.8, distance_km: 11, bearing_deg: 126, last_heard: ago(120) });

/** The cards' row with the satellites layer ticked on and the daemon's message of the ISS and SONATE-2 told. */
function make(rows: ReturnType<typeof station>[] = [], size: SizeClass = "desktop") {
  localStorage.setItem("NeoAPRS.layer.satellites", "on");
  forgetLayerTicks();
  const daemon = fakeDaemon({ now: NOW });
  const wrapper = mount(StationCards, { props: { rows, size }, global: withDaemon(daemon), attachTo: document.body });
  const tell = async (...ids: number[]) => {
    daemon.satelliteStore.handlers.satellites(
      satellitesMessage({
        cards: ids.map((id) =>
          id === 25544 ? satelliteCard({ path: "ARISS" }) : satelliteCard({ id, name: "SONATE-2", path: "" }),
        ),
      }),
    );
    await nextTick();
  };
  return { wrapper, daemon, layer: daemon.satellites, tell };
}

afterEach(() => {
  document.body.innerHTML = "";
  localStorage.clear();
  forgetLayerTicks();
});

describe("SatelliteCard in the cards' row", () => {
  it("shows a card for each satellite opened, oldest first, with its name, kind, path to copy and the table to tune", async () => {
    const page = make();
    page.layer.open(25544);
    page.layer.open(59112);
    await page.tell(25544, 59112);
    const cards = page.wrapper.findAll(".satcard");
    expect(cards.map((card) => card.find(".card-call").text())).toEqual(["ISS", "SONATE-2"]);
    const iss = cards[0];
    expect(iss?.find(".card-title .muted").text()).toBe("Satellite");
    expect(iss?.find(".copyfield code").text()).toBe("ARISS");
    expect(cards[1]?.find(".copyfield").exists()).toBe(false);
    expect(iss?.findAll(".satcard-tune tbody tr").map((row) => row.text())).toEqual([
      expect.stringContaining("437.834"),
      expect.stringContaining("437.816"),
    ]);
    expect(page.wrapper.find(".cards-closeall").exists()).toBe(true);
  });

  it("closes by its cross, and Close all closes the satellites' cards with the stations'", async () => {
    const page = make([car]);
    page.layer.open(25544);
    page.layer.open(59112);
    await page.tell(25544, 59112);
    await page.wrapper.findAll(".satcard")[1]?.find(".card-close").trigger("click");
    expect(page.layer.opened.value).toEqual([25544]);
    await page.wrapper.find(".cards-closeall").trigger("click");
    expect(page.layer.opened.value).toEqual([]);
    expect(page.wrapper.emitted("closeAll")).toHaveLength(1);
  });

  it("on a phone is the one sheet: a satellite's card closes the others", async () => {
    const page = make([car], "phone");
    page.layer.open(25544);
    await nextTick();
    expect(page.wrapper.emitted("closeAll")).toHaveLength(1);
    page.layer.open(59112);
    await nextTick();
    expect(page.layer.opened.value).toEqual([59112]);
  });
});
