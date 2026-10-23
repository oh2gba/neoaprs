import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import StationCards from "@/components/StationCards.vue";
import type { Aging } from "@/lib/aging";
import type { SizeClass } from "@/lib/layout";
import { SWIPE_MIN } from "@/lib/sheet";
import { cssRule } from "@/test/css";
import { NOW, ago, series, station, weatherStation } from "@/test/fixtures";

const aging: Aging = { timeouts: new Map(), defaultMin: 0 };
const car = station("OH2ZMA-9", { symbol_name: "Car", lat: 60.1, lon: 24.8, distance_km: 11, bearing_deg: 126, last_heard: ago(120) });
const wx = (call: string) => weatherStation(call);

function make(rows: ReturnType<typeof station>[], size: SizeClass = "desktop") {
  return mount(StationCards, { props: { rows, size, now: NOW, aging, weatherSeries: new Map() }, attachTo: document.body });
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
    expect(wrapper.find(".wx-span").exists()).toBe(false); // (no switch of the span: it is the one of all the cards)
    expect(wrapper.emitted("weather")).toEqual([
      ["OH2ZWA", 24],
      ["OH2ZWB", 24],
    ]); // (each weather card asks for its graphs)
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

describe("StationCards: several weather cards, to be compared", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => document.body.replaceChildren());

  /** A series whose temperature runs from `low` to `high`. */
  function cold(call: string, low: number, high: number) {
    const answer = series(call, 24, 6);
    answer.points = answer.points.map((p, i) => [p[0], i % 2 === 0 ? low : high, p[2], p[3], p[4], p[5], p[6]]);
    return answer;
  }
  const yAxes = (wrapper: ReturnType<typeof make>) =>
    wrapper.findAll(".card").map((card) =>
      card
        .find(".trend .trend-grid")
        .findAll("g > text")
        .slice(0, 6)
        .map((t) => t.text()),
    );
  const mountWith = (rows: ReturnType<typeof station>[], answers: ReturnType<typeof series>[]) =>
    mount(StationCards, {
      props: { rows, size: "desktop", now: NOW, aging, weatherSeries: new Map(answers.map((a) => [a.call, a])) },
      attachTo: document.body,
    });

  it("keeps the graphs on a compact weather card, small, and asks for them", () => {
    const wrapper = mountWith([wx("OH2ZWA"), wx("OH2ZWB")], [series("OH2ZWA", 24, 8), series("OH2ZWB", 24, 8)]);
    expect(wrapper.findAll(".card.compact")).toHaveLength(2);
    expect(wrapper.findAll(".card")[0]?.findAll(".trend.compact").length).toBeGreaterThanOrEqual(3);
    expect(wrapper.find(".wx-line").exists()).toBe(true);
    expect(wrapper.emitted("weather")).toEqual([
      ["OH2ZWA", 24],
      ["OH2ZWB", 24],
    ]);
  });

  it("draws every graph of the weather cards on the same value axis while two or more are open: -5 to +12 degrees on all", () => {
    const wrapper = mountWith([wx("OH2ZWA"), wx("OH2ZWB")], [cold("OH2ZWA", -5, -2), cold("OH2ZWB", 8, 12)]);
    const [first, second] = yAxes(wrapper);
    expect(first).toEqual(second);
    expect(first?.[0]).toBe("-10"); // (the axis of the lowest and the highest of both, in round numbers: -10 to 20)
    expect(first?.at(-1)).toBe("20");
  });

  it("gives a card of its own the scale of its own values, as before", () => {
    const wrapper = mountWith([wx("OH2ZWA")], [cold("OH2ZWA", -5, -2)]);
    expect(wrapper.find(".card").classes()).not.toContain("compact");
    const labels = wrapper
      .find(".trend .trend-grid")
      .findAll("g > text")
      .map((t) => t.text());
    expect(labels.filter((l) => !l.includes(":")).some((label) => Number(label) >= 10)).toBe(false);
  });

  it("goes back to the card's own scale when the other weather card is closed, and does not share with a card that is not a weather station", async () => {
    const wrapper = mountWith([wx("OH2ZWA"), wx("OH2ZWB")], [cold("OH2ZWA", -5, -2), cold("OH2ZWB", 8, 12)]);
    await wrapper.setProps({ rows: [wx("OH2ZWA"), car] });
    expect(wrapper.findAll(".card.compact")).toHaveLength(2);
    const labels =
      wrapper
        .findAll(".card")[0]
        ?.find(".trend .trend-grid")
        .findAll("g > text")
        .map((t) => t.text()) ?? [];
    expect(labels.filter((l) => !l.includes(":")).some((label) => Number(label) >= 10)).toBe(false);
  });

  it("shares the time axis and the span: the same hours under every card, and one switch for all", () => {
    localStorage.setItem("NeoAPRS.wxhours", "168");
    const wrapper = mountWith([wx("OH2ZWA"), wx("OH2ZWB")], [series("OH2ZWA", 168, 8), series("OH2ZWB", 168, 8)]);
    expect(wrapper.emitted("weather")).toEqual([
      ["OH2ZWA", 168],
      ["OH2ZWB", 168],
    ]);
    const labels = wrapper.findAll(".card").map((card) =>
      card
        .findAll(".trend-grid text")
        .map((t) => t.text())
        .filter((t) => /[A-Z][a-z]{2} \d|:/.test(t)),
    );
    expect(labels[0]).toEqual(labels[1]);
  });

  it("is not squeezed: a compact card has the one size, whatever the number of cards (flex: none, no height of its own)", () => {
    expect(cssRule(".cardstack .card.compact")).toMatch(/flex:\s*none/);
    expect(cssRule(".cardstack .card.compact")).not.toMatch(/max-height|min-height|flex-shrink|height:/);
    for (const rule of [cssRule(".card.compact .card-head"), cssRule(".card.compact .card-fields"), cssRule(".trend.compact")])
      expect(rule).not.toMatch(/%|vh|calc|clamp/);
    expect(cssRule(".cardstack")).not.toMatch(/overflow/);
  });
});

describe("StationCards: the column that does not fit", () => {
  afterEach(() => {
    document.body.replaceChildren();
    for (const name of ["clientHeight", "offsetHeight"]) Reflect.deleteProperty(HTMLElement.prototype, name);
  });

  /** A map `room` px high, and cards that are `each` px high (Close all is 30). */
  function laidOut(room: number, each: number) {
    Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => room });
    Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
      configurable: true,
      get(this: HTMLElement) {
        return this.classList.contains("card") ? each : 30;
      },
    });
  }

  it("says so when the cards are taller than the map has room for (114 px of it is for the zoom buttons and the corner)", async () => {
    laidOut(700, 150);
    const wrapper = make([wx("OH2ZWA"), wx("OH2ZWB"), wx("OH2ZWC"), wx("OH2ZWD")]);
    await nextTick();
    await nextTick();
    expect(wrapper.emitted("overflow")).toHaveLength(1); // 4 cards of 150 px and 3 gaps in 586 px
  });

  it("says nothing when they fit, or when there is one card, or on a phone", async () => {
    laidOut(700, 130);
    const fits = make([wx("OH2ZWA"), wx("OH2ZWB"), wx("OH2ZWC"), wx("OH2ZWD")]);
    await nextTick();
    await nextTick();
    expect(fits.emitted("overflow")).toBeUndefined();
    laidOut(100, 500);
    const alone = make([wx("OH2ZWA")]);
    await nextTick();
    expect(alone.emitted("overflow")).toBeUndefined();
    const phone = make([wx("OH2ZWA"), wx("OH2ZWB")], "phone");
    await nextTick();
    expect(phone.emitted("overflow")).toBeUndefined();
  });
});

describe("StationCards: Message these N", () => {
  const button = (wrapper: ReturnType<typeof make>) => wrapper.find(".cards-message");

  it("is beside Close all, says how many of the cards are for stations that can be messaged, and sends their calls", async () => {
    const wrapper = make([car, station("OH2RDG"), station("OH2RDH")]);
    expect(wrapper.find(".cards-actions .cards-closeall").exists()).toBe(true);
    expect(button(wrapper).text()).toBe("Message these 3");
    await button(wrapper).trigger("click");
    expect(wrapper.emitted("messageAll")).toEqual([[["OH2ZMA-9", "OH2RDG", "OH2RDH"]]]);
  });

  it("is not there with fewer than two cards, and not with a single card that can be messaged among several", () => {
    expect(button(make([car])).exists()).toBe(false);
    expect(make([car]).find(".cards-actions").exists()).toBe(false);
    const one = make([car, station("OH2OBJ", { can_message: false })]);
    expect(one.find(".cards-closeall").exists()).toBe(true);
    expect(button(one).exists()).toBe(false);
  });

  it("leaves out what cannot be messaged: ourselves, our objects, objects and items of others, and a station the daemon says cannot be", () => {
    const wrapper = make([
      car,
      station("OH2GBA", { is_me: true }),
      station("NETCTRL", { own: true, kind: "object" }),
      station("HAMFEST", { kind: "item" }),
      station("OH2NOT", { can_message: false }),
      station("OH2RDG"),
    ]);
    expect(button(wrapper).text()).toBe("Message these 2");
  });

  it("counts again when a card is closed, and goes when one is left that can be messaged", async () => {
    const wrapper = make([car, station("OH2RDG"), station("OH2RDH")]);
    await wrapper.setProps({ rows: [car, station("OH2RDG")] });
    expect(button(wrapper).text()).toBe("Message these 2");
    await wrapper.setProps({ rows: [car, station("OH2ZWX", { can_message: false })] });
    expect(button(wrapper).exists()).toBe(false);
  });

  it("is not on a phone, which has one card", () => {
    expect(
      make([car, station("OH2RDG")], "phone")
        .find(".cards-actions")
        .exists(),
    ).toBe(false);
  });
});
