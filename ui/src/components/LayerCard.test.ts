import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { computed, nextTick, shallowRef } from "vue";
import StationCards from "@/components/StationCards.vue";
import type { LayerTraffic, OpenThing } from "@/composables/useLayerThings";
import type { SizeClass } from "@/lib/layout";
import { fakeDaemon, withDaemon } from "@/test/context";
import { NOW, ago, station } from "@/test/fixtures";
import { AIRCRAFT_SHAPES } from "@/lib/layers/aircraftshapes";
import { MARKS } from "@/lib/layers/marks";
import { aircraft, ship } from "@/test/layerfixtures";

const car = station("OH2ZMA-9", { lat: 60.1, lon: 24.8, distance_km: 11, bearing_deg: 126, last_heard: ago(120) });

/** The page's traffic with a card a test opens and closes. */
function fakeTraffic(first: OpenThing | null) {
  const open = shallowRef<OpenThing | null>(first);
  const close = vi.fn(() => {
    const was = open.value !== null;
    open.value = null;
    return was;
  });
  const traffic: LayerTraffic = {
    looked: computed(() => []),
    tables: computed(() => new Map()),
    card: open,
    trail: computed(() => []),
    open: () => undefined,
    close,
  };
  return { traffic, open, close };
}

function make(thing: OpenThing | null, rows: ReturnType<typeof station>[] = [], size: SizeClass = "desktop") {
  const fake = fakeTraffic(thing);
  const daemon = fakeDaemon({ traffic: fake.traffic, now: NOW });
  const wrapper = mount(StationCards, { props: { rows, size }, global: withDaemon(daemon), attachTo: document.body });
  return { wrapper, ...fake };
}

const plane: OpenThing = { layer: "aircraft", thing: aircraft({ at: ago(12) }), source: "adsblol" };
const boat: OpenThing = { layer: "ships", thing: ship({ at: ago(65), name: "" }), source: "receiver" };
const fields = (card: Element | null) =>
  [...(card?.querySelectorAll("dt:not(.layercard-room)") ?? [])].map((dt) => `${dt.textContent}: ${dt.nextElementSibling?.textContent}`);

afterEach(() => document.body.replaceChildren());

describe("the card of an aircraft or a ship", () => {
  it("is a card of the cards' row, with the frame, the head and the cross of a station's card, and what the source says", () => {
    const { wrapper } = make(plane);
    const card = wrapper.find(".cardstack > .card.layercard");
    expect(card.exists()).toBe(true);
    expect(card.find(".card-head .card-call").text()).toBe("FIN7AB");
    expect(card.find(".card-head .muted").text()).toBe("Aircraft");
    expect(card.find(".card-head .card-close").exists()).toBe(true);
    expect(fields(card.element)).toEqual([
      "Registration: OH-LZA",
      "Type: AIRBUS A-321",
      "Altitude: 2438 m",
      "Speed: 421 km/h",
      "Heading: 225° SW",
      "Age: 12 s",
      "Source: adsb.lol",
    ]);
  });

  it("keeps the room of every label it may have in an unseen first row, so that the values stand still while a row comes and goes", () => {
    const room = make(plane).wrapper.find(".layercard .card-fields > dt.layercard-room");
    expect(room.attributes("aria-hidden")).toBe("true");
    expect(room.findAll("span").map((label) => label.text())).toEqual([
      "Registration",
      "Type",
      "From",
      "To",
      "Altitude",
      "Vertical speed",
      "Speed",
      "Heading",
      "Age",
      "Source",
    ]);
    expect(room.element.nextElementSibling?.matches("dd.layercard-room")).toBe(true);
    expect(room.element.previousElementSibling).toBeNull();
  });

  it("has the aircraft's own shape in its head, pointing north, also where it gives no direction, and a ship's hull", () => {
    const glider: OpenThing = { layer: "aircraft", thing: aircraft({ category: "B1", designator: "", heading_deg: null }), source: "radarcape" };
    const head = (thing: OpenThing) => make(thing).wrapper.find(".layercard .card-head .layercard-mark svg");
    expect(head(glider).find("path").attributes("d")).toBe(AIRCRAFT_SHAPES.glider.d);
    expect(head(glider).attributes("viewBox")).toBe(AIRCRAFT_SHAPES.glider.viewBox);
    expect(head(plane).find("path").attributes("d")).toBe(AIRCRAFT_SHAPES.airliner.d);
    expect(head(boat).find("path").attributes("d")).toBe(MARKS.hull.d);
  });

  it("has a ship's rows, named by its MMSI where it gave no name, from the own receiver", () => {
    const { wrapper } = make(boat);
    const card = wrapper.find(".layercard");
    expect(card.find(".card-call").text()).toBe("MMSI 230123456");
    expect(card.find(".muted").text()).toBe("Ship");
    expect(fields(card.element)).toEqual([
      "Kind: Passenger ship",
      "Speed: 22 km/h",
      "Course: 182° S",
      "Destination: TALLINN",
      "Age: 1 min",
      "Source: My own receiver",
    ]);
  });

  it("has nothing of a station: no pin, no Message, no Forget, no Details, no packets", () => {
    const { wrapper } = make(plane);
    const card = wrapper.find(".layercard");
    for (const part of [".card-pin", ".msgbtn", "details", ".stationpackets", "[data-call]"]) expect(card.find(part).exists()).toBe(false);
    expect(card.text()).not.toMatch(/Message|Forget|Details|Path/);
  });

  it("closes with its cross", async () => {
    const { wrapper, close } = make(plane);
    await wrapper.find(".layercard .card-close").trigger("click");
    expect(close).toHaveBeenCalled();
    expect(wrapper.find(".layercard").exists()).toBe(false);
  });

  it("stands after the station cards, and Close all closes it with them", async () => {
    const { wrapper, close } = make(plane, [car]);
    expect(wrapper.findAll(".cardstack > .card").map((card) => card.classes().includes("layercard"))).toEqual([false, true]);
    await wrapper.find(".cards-closeall").trigger("click");
    expect(close).toHaveBeenCalled();
    expect(wrapper.emitted("closeAll")).toHaveLength(1);
  });

  it("alone, has no Close all", () => {
    expect(make(plane).wrapper.find(".cards-closeall").exists()).toBe(false);
  });
});

describe("the card of a thing on a phone", () => {
  it("is the one bottom sheet, folded to its head, and a swipe down on it closes it", async () => {
    const { wrapper, close } = make(plane, [], "phone");
    expect(wrapper.find(".cardstack").classes()).toContain("sheet");
    expect(wrapper.find(".sheet-grip").exists()).toBe(true);
    const grip = wrapper.find(".sheet-grip").element;
    grip.dispatchEvent(new MouseEvent("pointerdown", { clientY: 100, bubbles: true }));
    grip.dispatchEvent(new MouseEvent("pointerup", { clientY: 300, bubbles: true }));
    await nextTick();
    expect(close).toHaveBeenCalled();
  });

  it("closes a station's card as it opens, and is closed when a station's card opens", async () => {
    const { wrapper, open, close } = make(null, [car], "phone");
    open.value = plane;
    await nextTick();
    expect(wrapper.emitted("closeAll")).toHaveLength(1);
    await wrapper.setProps({ rows: [] });
    await wrapper.setProps({ rows: [station("OH2XYZ", { lat: 60.2, lon: 24.9 })] });
    expect(close).toHaveBeenCalled();
    expect(open.value).toBeNull();
  });

  it("on a desktop stands beside a station's card that opens", async () => {
    const { wrapper, open, close } = make(plane, [], "desktop");
    await wrapper.setProps({ rows: [car] });
    expect(close).not.toHaveBeenCalled();
    expect(open.value).not.toBeNull();
    expect(wrapper.emitted("closeAll")).toBeUndefined();
  });
});
