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

describe("StationCards: the row of a tablet and a desktop", () => {
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

  it("shows several cards side by side, each the whole card, the oldest first (the style puts it at the left), each with its own close, and Close all over the map", async () => {
    const wrapper = make([wx("OH2ZWA"), wx("OH2ZWB"), car]);
    expect(wrapper.findAll(".card").map((c) => c.find("strong").text())).toEqual(["OH2ZWA", "OH2ZWB", "OH2ZMA-9"]);
    expect(wrapper.findAll(".card.compact")).toHaveLength(0);
    expect(wrapper.findAll(".card .card-foot")).toHaveLength(3); // (the buttons of a whole card)
    expect(wrapper.findAll(".card").every((card) => card.text().includes("Details"))).toBe(true);
    expect(wrapper.find(".card-more").exists()).toBe(false);
    expect(wrapper.findAll(".card .wx-span")).toHaveLength(2); // (the switch of the graphs: a weather card is the whole weather card)
    expect(wrapper.find(".cardstack .cards-actions").exists()).toBe(false); // (Close all is not in the row)
    await wrapper.findAll(".card")[1]?.find("button[aria-label='Close']").trigger("click");
    expect(wrapper.emitted("close")).toEqual([["OH2ZWB"]]);
    await wrapper.find(".cards-closeall").trigger("click");
    expect(wrapper.emitted("closeAll")).toHaveLength(1);
  });

  it("has a card of the same facts alone and among others: nothing is taken away from it when another is opened", () => {
    const alone = make([car]);
    const among = make([car, wx("OH2ZWA")]);
    expect(among.findAll(".card")[0]?.html()).toBe(alone.find(".card").html());
    const wxAlone = make([wx("OH2ZWA")]);
    const wxAmong = make([wx("OH2ZWA"), car]);
    expect(wxAmong.findAll(".card")[0]?.html()).toBe(wxAlone.find(".card").html());
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

  /** A series whose temperature runs from `low` to `high`, its wind from 0 to `wind`. */
  function cold(call: string, low: number, high: number, wind = 6) {
    const answer = series(call, 24, 6);
    answer.points = answer.points.map((p, i) => [p[0], i % 2 === 0 ? low : high, p[2], p[3], i % 2 === 0 ? wind : 3, p[5], p[6]]);
    return answer;
  }
  type Wrapper = ReturnType<typeof make>;
  /** The labels of the value axis of each graph of each card, by the graph's title. */
  const axes = (wrapper: Wrapper) =>
    wrapper.findAll(".card").map((card) =>
      Object.fromEntries(
        card.findAll(".trend").map((t) => [
          t.find("figcaption span").text(),
          t
            .findAll(".trend-grid g > text")
            .map((x) => x.text())
            .filter((x) => !x.includes(":")),
        ]),
      ),
    );
  const mountWith = (rows: ReturnType<typeof station>[], answers: ReturnType<typeof series>[]) =>
    mount(StationCards, {
      props: { rows, size: "desktop", now: NOW, aging, weatherSeries: new Map(answers.map((a) => [a.call, a])) },
      attachTo: document.body,
    });
  const mapOf = (...answers: ReturnType<typeof series>[]) => new Map(answers.map((a) => [a.call, a] as const));

  it("keeps every weather card the whole weather card with its graphs, the switch of the span and the asking of the daemon", () => {
    const wrapper = mountWith([wx("OH2ZWA"), wx("OH2ZWB")], [series("OH2ZWA", 24, 8), series("OH2ZWB", 24, 8)]);
    for (const card of wrapper.findAll(".card")) {
      expect(card.findAll(".trend")).toHaveLength(4);
      expect(card.find(".wx-span").exists()).toBe(true);
      expect(card.find(".wx-now").exists()).toBe(true);
    }
    expect(wrapper.emitted("weather")).toEqual([
      ["OH2ZWA", 24],
      ["OH2ZWB", 24],
    ]);
  });

  it("draws every graph of the weather cards on the same value axis while two or more are open", () => {
    const wrapper = mountWith([wx("OH2ZWA"), wx("OH2ZWB")], [cold("OH2ZWA", -5, -2, 6), cold("OH2ZWB", 8, 12, 30)]);
    const [first, second] = axes(wrapper);
    expect(first).toEqual(second);
    expect(first?.Temperature?.[0]).toBe("-5"); // (the lowest and the highest of both in round numbers: -5 to 15)
    expect(first?.Temperature?.at(-1)).toBe("15");
    expect(first?.["Wind and gusts"]?.at(-1)).not.toBe(first?.Temperature?.at(-1));
    expect(Number(first?.["Wind and gusts"]?.at(-1))).toBeGreaterThanOrEqual(30);
  });

  it("shares when the second series arrives later: the first card's axes are the two cards' together as soon as it is there", async () => {
    const a = cold("OH2ZWA", -5, -2, 6);
    const b = cold("OH2ZWB", 8, 12, 30);
    const wrapper = mountWith([wx("OH2ZWA"), wx("OH2ZWB")], [a]);
    const before = axes(wrapper)[0];
    expect(before?.Temperature?.at(-1)).not.toBe("15"); // (only its own so far)
    await wrapper.setProps({ weatherSeries: mapOf(a, b) });
    const [first, second] = axes(wrapper);
    expect(first).toEqual(second);
    expect(first?.Temperature?.at(-1)).toBe("15");
    // and again when the first one's series is renewed with other values (a new observation)
    await wrapper.setProps({ weatherSeries: mapOf(cold("OH2ZWA", -25, -2, 6), b) });
    const [renewed, other] = axes(wrapper);
    expect(renewed).toEqual(other);
    expect(renewed?.Temperature?.[0]).toBe("-30");
  });

  it("shares whichever order the series come in, and when the cards are opened one after the other", async () => {
    const a = cold("OH2ZWA", -5, -2, 6);
    const b = cold("OH2ZWB", 8, 12, 30);
    const wrapper = mountWith([wx("OH2ZWA")], [a, b]);
    await wrapper.setProps({ rows: [wx("OH2ZWA"), wx("OH2ZWB")] });
    const [first, second] = axes(wrapper);
    expect(first).toEqual(second);
    const reversed = mountWith([wx("OH2ZWB"), wx("OH2ZWA")], [b, a]);
    expect(axes(reversed)[0]?.Temperature).toEqual(first?.Temperature);
  });

  it("gives a card of its own the scale of its own values, as before", () => {
    const wrapper = mountWith([wx("OH2ZWA")], [cold("OH2ZWA", -5, -2)]);
    const labels = axes(wrapper)[0]?.Temperature ?? [];
    expect(labels.at(-1)).not.toBe("15");
    expect(labels.every((label) => Number(label) < 10)).toBe(true);
  });

  it("goes back to the card's own scale when the other weather card is closed, and does not share with a card that is not a weather station", async () => {
    const wrapper = mountWith([wx("OH2ZWA"), wx("OH2ZWB")], [cold("OH2ZWA", -5, -2), cold("OH2ZWB", 8, 12)]);
    await wrapper.setProps({ rows: [wx("OH2ZWA"), car] });
    expect(wrapper.findAll(".card")).toHaveLength(2);
    expect((axes(wrapper)[0]?.Temperature ?? []).every((label) => Number(label) < 10)).toBe(true);
  });

  it("shares the time axis and the span: the same hours under every card, and one switch for all", async () => {
    localStorage.setItem("NeoAPRS.wxhours", "168");
    const wrapper = mountWith([wx("OH2ZWA"), wx("OH2ZWB")], [series("OH2ZWA", 168, 8), series("OH2ZWB", 168, 8)]);
    expect(wrapper.emitted("weather")).toEqual([
      ["OH2ZWA", 168],
      ["OH2ZWB", 168],
    ]);
    const hours = () =>
      wrapper.findAll(".card").map((card) =>
        card
          .findAll(".trend-grid text")
          .map((t) => t.text())
          .filter((t) => /[A-Z][a-z]{2} \d|:/.test(t)),
      );
    expect(hours()[0]).toEqual(hours()[1]);
    await wrapper.findAll(".card")[0]?.findAll(".wx-span .btn")[0]?.trigger("click"); // 24 h in the first card
    expect(wrapper.emitted("weather")?.slice(-2)).toEqual([
      ["OH2ZWA", 24],
      ["OH2ZWB", 24],
    ]); // (the second card follows: one span for all)
  });
});

describe("StationCards: a row that does not fit", () => {
  afterEach(() => {
    document.body.replaceChildren();
    for (const name of ["clientWidth", "offsetWidth"]) Reflect.deleteProperty(HTMLElement.prototype, name);
  });

  /** A map whose row has `room` px between its edges, and cards that are `each` px wide. */
  function laidOut(room: number, each: number) {
    Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => room });
    Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, get: () => each });
  }

  it("says so when the cards are wider together than the map has room for (20 px of it are the margins), and a card is never made narrower", async () => {
    laidOut(1000, 340);
    const three = make([wx("OH2ZWA"), wx("OH2ZWB"), car]); // 3 x 340 + 2 x 8 = 1036 in 980
    await nextTick();
    await nextTick();
    expect(three.emitted("overflow")).toHaveLength(1);
    expect(cssRule(".cardstack .card")).toMatch(/flex:\s*none/);
  });

  it("says nothing when they fit, or when there is one card, or on a phone", async () => {
    laidOut(1000, 320);
    const fits = make([wx("OH2ZWA"), wx("OH2ZWB"), car]); // 3 x 320 + 16 = 976 in 980
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

  it("has every card one width, whatever the number of cards: flex: none, a width of its own that does not depend on the others", () => {
    const rule = cssRule(".cardstack .card");
    expect(rule).toMatch(/flex:\s*none/);
    expect(rule).toMatch(/width:\s*min\(340px, 100%\)/);
    expect(cssRule(".cardstack")).toMatch(/flex-direction|align-items:\s*flex-end/);
    expect(cssRule(".cardstack")).not.toMatch(/flex-direction:\s*column/);
    expect(cssRule(".cardstack")).not.toMatch(/overflow/);
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
