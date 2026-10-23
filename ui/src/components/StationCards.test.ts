import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import StationCards from "@/components/StationCards.vue";
import type { Aging } from "@/lib/aging";
import type { SizeClass } from "@/lib/layout";
import { SWIPE_MIN } from "@/lib/sheet";
import { NOW, ago, station, weatherStation } from "@/test/fixtures";

const aging: Aging = { timeouts: new Map(), defaultMin: 0 };
const car = station("OH2ZMA-9", { symbol_name: "Car", lat: 60.1, lon: 24.8, distance_km: 11, bearing_deg: 126, last_heard: ago(120) });
const wx = (call: string) => weatherStation(call);

function make(rows: ReturnType<typeof station>[], size: SizeClass = "desktop") {
  return mount(StationCards, { props: { rows, size, now: NOW, aging, weatherSeries: null }, attachTo: document.body });
}

const pointer = (wrapper: ReturnType<typeof make>, type: "pointerdown" | "pointerup", y: number) =>
  wrapper.find(".sheet-grip").element.dispatchEvent(new MouseEvent(type, { clientY: y, bubbles: true }));

describe("StationCards: the column of a tablet and a desktop", () => {
  it("shows nothing without a card", () => {
    expect(make([]).find(".cardstack").exists()).toBe(false);
  });

  it("shows one card whole, with no Close all and no grip", () => {
    const wrapper = make([car]);
    expect(wrapper.findAll(".card")).toHaveLength(1);
    expect(wrapper.find(".card").classes()).not.toContain("compact");
    expect(wrapper.find(".cards-closeall").exists()).toBe(false);
    expect(wrapper.find(".sheet-grip").exists()).toBe(false);
    expect(wrapper.find(".cardstack").classes()).not.toContain("sheet");
    expect(wrapper.text()).toContain("Details");
  });

  it("shows several cards compact, the oldest first in the page (the style puts it at the bottom), each with its own close, and a Close all", async () => {
    const wrapper = make([wx("OH2ZWA"), wx("OH2ZWB"), car]);
    expect(wrapper.findAll(".card").map((c) => c.find("strong").text())).toEqual(["OH2ZWA", "OH2ZWB", "OH2ZMA-9"]);
    expect(wrapper.findAll(".card.compact")).toHaveLength(3);
    expect(wrapper.text()).not.toContain("Details");
    expect(wrapper.find(".card-foot").exists()).toBe(false);
    expect(wrapper.find(".wx-span").exists()).toBe(false); // (no graphs, no asking the daemon for them)
    expect(wrapper.emitted("weather")).toBeUndefined();
    await wrapper.findAll(".card")[1]?.find("button[aria-label='Close']").trigger("click");
    expect(wrapper.emitted("close")).toEqual([["OH2ZWB"]]);
    await wrapper.find(".cards-closeall").trigger("click");
    expect(wrapper.emitted("closeAll")).toHaveLength(1);
  });

  it("has More on a compact card, which is for making it the only one, whole", async () => {
    const wrapper = make([wx("OH2ZWA"), car]);
    await wrapper.findAll(".card")[0]?.find(".card-more").trigger("click");
    expect(wrapper.emitted("only")).toEqual([["OH2ZWA"]]);
    const alone = make([car]);
    expect(alone.find(".card-more").exists()).toBe(false);
  });

  it("goes on with what a whole card says: Message, Forget, and asking for the weather", async () => {
    const wrapper = make([wx("OH2ZWA")]);
    expect(wrapper.emitted("weather")?.[0]?.[0]).toBe("OH2ZWA");
    await wrapper
      .findAll(".card .btn")
      .find((b) => b.text() === "Message")
      ?.trigger("click");
    expect(wrapper.emitted("message")).toEqual([["OH2ZWA"]]);
  });
});

describe("StationCards: the bottom sheet of a phone", () => {
  it("is a sheet with a grip, folded, and has the card's own close button", async () => {
    const wrapper = make([car], "phone");
    expect(wrapper.find(".cardstack").classes()).toEqual(expect.arrayContaining(["sheet"]));
    expect(wrapper.find(".cardstack").classes()).not.toContain("expanded");
    expect(wrapper.find(".sheet-grip").attributes("aria-expanded")).toBe("false");
    expect(wrapper.find(".cards-closeall").exists()).toBe(false);
    await wrapper.find("button[aria-label='Close']").trigger("click");
    expect(wrapper.emitted("close")).toEqual([["OH2ZMA-9"]]);
  });

  it("opens with a tap on the grip and folds with the next", async () => {
    const wrapper = make([car], "phone");
    await wrapper.find(".sheet-grip").trigger("click");
    expect(wrapper.find(".cardstack").classes()).toContain("expanded");
    expect(wrapper.find(".sheet-grip").attributes("aria-label")).toBe("Fold the card");
    await wrapper.find(".sheet-grip").trigger("click");
    expect(wrapper.find(".cardstack").classes()).not.toContain("expanded");
  });

  it("opens with a swipe up, folds with a swipe down, and a swipe down on the folded sheet closes the card", async () => {
    const wrapper = make([car], "phone");
    pointer(wrapper, "pointerdown", 500);
    pointer(wrapper, "pointerup", 500 - SWIPE_MIN - 20);
    await wrapper.find(".sheet-grip").trigger("click"); // (the click that follows the swipe is not a tap)
    expect(wrapper.find(".cardstack").classes()).toContain("expanded");
    pointer(wrapper, "pointerdown", 300);
    pointer(wrapper, "pointerup", 300 + SWIPE_MIN + 40);
    await wrapper.find(".sheet-grip").trigger("click");
    expect(wrapper.find(".cardstack").classes()).not.toContain("expanded");
    expect(wrapper.emitted("close")).toBeUndefined();
    pointer(wrapper, "pointerdown", 300);
    pointer(wrapper, "pointerup", 300 + SWIPE_MIN + 40);
    expect(wrapper.emitted("close")).toEqual([["OH2ZMA-9"]]);
  });

  it("treats a short move of the finger as a tap, and ignores a lift without a touch before it", async () => {
    const wrapper = make([car], "phone");
    pointer(wrapper, "pointerup", 100);
    pointer(wrapper, "pointerdown", 300);
    pointer(wrapper, "pointerup", 304);
    await wrapper.find(".sheet-grip").trigger("click");
    expect(wrapper.find(".cardstack").classes()).toContain("expanded");
  });

  it("is folded again for another station's card", async () => {
    const wrapper = make([car], "phone");
    await wrapper.find(".sheet-grip").trigger("click");
    await wrapper.setProps({ rows: [station("OH2RDG")] });
    expect(wrapper.find(".cardstack").classes()).not.toContain("expanded");
  });
});
