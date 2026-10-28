import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import StationCard from "@/components/StationCard.vue";
import type { Aging } from "@/lib/aging";
import { cssRule } from "@/test/css";
import { NOW, ago, series, station, weatherStation } from "@/test/fixtures";

const row = station("OH2PU-9", {
  symbol_name: "Car",
  lat: 60.19908,
  lon: 24.65007,
  distance_km: 16.2,
  bearing_deg: 282,
  course_deg: 356,
  speed_kmh: 42,
  altitude_m: 31,
  last_heard: ago(120),
  last_position_at: ago(600),
  last_status: "on air",
  last_comment: "QRV D-STAR",
  last_path: ["OH2RCH-2*", "WIDE2-1"],
  packets: 19,
});

afterEach(() => vi.useRealTimers());

const fieldsOf = (wrapper: ReturnType<typeof mount>) =>
  Object.fromEntries(wrapper.findAll("dt").map((dt) => [dt.text(), dt.element.nextElementSibling?.textContent?.trim()]));

describe("StationCard", () => {
  it("shows the main facts of the row, and the rest under Details", () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW } });
    const text = wrapper.text();
    for (const wanted of [
      "OH2PU-9",
      "Car",
      "60.19908 N 24.65007 E",
      "16 km, 282° WNW",
      "42 km/h, course 356° N",
      "31 m",
      "RF 2 min ago",
      "on air",
      "QRV D-STAR",
    ]) {
      expect(text, wanted).toContain(wanted);
    }
    const details = wrapper.find("details");
    expect(details.find("summary").text()).toBe("Details");
    expect(details.attributes("open")).toBeUndefined();
    expect(details.text()).toContain("OH2RCH-2*,WIDE2-1");
    expect(details.text()).toContain("19");
    expect(wrapper.find("dl").text()).not.toContain("OH2RCH-2*,WIDE2-1");
  });

  it("says the symbol once, with its picture and name in the head, and not as a row with the table and code letters", () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW } });
    expect(wrapper.find(".card-head .symicon").exists()).toBe(true);
    expect(wrapper.find(".card-head").text()).toContain("Car");
    expect(rowsOf(wrapper)).not.toContain("Symbol");
    expect(wrapper.text()).not.toContain("Car />");
  });

  it("says when it was heard as a time ago, the full time on hover", () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW } });
    const heard = wrapper.findAll("dt").find((dt) => dt.text() === "Last heard")?.element.nextElementSibling;
    expect(heard?.textContent?.trim()).toBe("RF 2 min ago");
    expect(heard?.getAttribute("title")).toMatch(/^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/);
  });
  it("shows the data extensions, the locator and the telemetry of a station, a line each, and nothing for one that has none", () => {
    const plain = fieldsOf(mount(StationCard, { props: { row, now: NOW } }));
    for (const label of ["PHG", "Range", "Locator", "Telemetry", "Bits"]) expect(plain, label).not.toHaveProperty(label);
    const detailed = station("OH2PU-9", {
      extensions: {
        phg: { power_w: 25, height_m: 6.1, gain_db: 3, direction_deg: 90, range_km: 12.8 },
        range_km: 80.5,
        dfs: null,
        df_bearing: null,
        area: null,
      },
      locator: { grid: "IO91sx", lat: 51.97917, lon: -0.45833, symbol_table: "/", symbol_code: "-" },
      telemetry: {
        sequence: 5,
        channels: [{ name: "Battery", unit: "v/100", raw: 199, value: 1034.8 }],
        bits: [{ name: "Camra", on: true }],
        project: "",
        comment: "",
      },
      telemetry_at: ago(30),
    });
    const fields = fieldsOf(mount(StationCard, { props: { row: detailed, now: NOW } }));
    expect(fields.PHG).toBe("25 W, 6 m, 3 dB, range 13 km");
    expect(fields.Range).toBe("81 km");
    expect(fields.Locator).toBe("IO91sx, 51.97917 N 0.45833 W");
    expect(fields.Telemetry).toBe("#5: Battery 1034.8 v/100");
    expect(fields.Bits).toBe("Camra on");
  });

  it("says in one line how its packets reach us, and keeps the routes, the counts and the best route for the details", () => {
    const heard = station("OH2PU-9", {
      last_route: "via OH2RCH-1 → OH2RCH-3",
      heard_direct: 12,
      heard_via: [
        ["OH2RCH-2", 30],
        ["OH2RCH-3", 4],
      ],
      heard_rf_gated: 2,
      best_route: "via OH2RCH-2",
      suggested_path: "OH2RCH-2",
    });
    const wrapper = mount(StationCard, { props: { row: heard, now: NOW } });
    const fields = Object.fromEntries(wrapper.findAll("dt").map((dt) => [dt.text(), dt.element.nextElementSibling?.textContent?.trim()]));
    expect(fields["Reached us"]).toBe("via OH2RCH-1 → OH2RCH-3");
    expect(wrapper.findAll("dt").filter((dt) => dt.text() === "Reached us")).toHaveLength(1);
    expect(
      wrapper
        .find("dl")
        .findAll("dt")
        .map((dt) => dt.text()),
    ).not.toEqual(expect.arrayContaining(["Route", "Heard", "Best route"]));
    expect(fields["Heard"]).toBe("12 direct, 30 via OH2RCH-2, 4 via OH2RCH-3, 2 via an iGate");
    expect(fields["Best route"]).toBe("via OH2RCH-2; send by OH2RCH-2");
    expect(wrapper.find("details").text()).toContain("Best route");
  });

  it("says direct for a station heard direct, and never splits a callsign over two lines", () => {
    const wrapper = mount(StationCard, { props: { row: station("OH2PU-9", { last_route: "direct" }), now: NOW } });
    expect(wrapper.find(".route").text()).toBe("direct");
    const via = mount(StationCard, { props: { row, now: NOW } }).find(".route");
    expect(via.text()).toBe("via OH2RCH-2");
    expect(via.findAll(".nowrap").map((w) => w.text())).toEqual(["via", "OH2RCH-2"]);
  });
  it("leaves out the rows of a route that is not known", () => {
    const none = station("X", { last_route: "", heard_via: [], best_route: "", suggested_path: null, last_path: [] });
    const fields = fieldsOf(mount(StationCard, { props: { row: none, now: NOW } }));
    for (const label of ["Reached us", "Path", "Heard", "Best route"]) expect(fields, label).not.toHaveProperty(label);
    expect(fields).not.toHaveProperty("Direct");
  });
  const rowsOf = (wrapper: ReturnType<typeof mount>) => wrapper.findAll("dt").map((dt) => dt.text());
  const house = station("OH2DPN", {
    symbol_name: "House",
    symbol_code: "-",
    course_deg: null,
    speed_kmh: null,
    altitude_m: null,
    last_status: "",
    last_comment: "",
  });

  it("has the rows of a moving station: its speed with the course, the altitude, the status and the comment, in the order of the card, the rest under Details", () => {
    expect(rowsOf(mount(StationCard, { props: { row, now: NOW } }))).toEqual([
      "Last heard",
      "Position",
      "From us",
      "Speed",
      "Altitude",
      "Status",
      "Comment",
      "Reached us",
      "First heard",
      "Path",
      "Heard",
      "Best route",
      "Packets",
    ]);
  });
  it("leaves out the rows with nothing to say: no speed, altitude, status or comment for a house", () => {
    expect(rowsOf(mount(StationCard, { props: { row: house, now: NOW } }))).toEqual([
      "Last heard",
      "Position",
      "From us",
      "Reached us",
      "First heard",
      "Path",
      "Heard",
      "Best route",
      "Packets",
    ]);
  });
  it("leaves out what is not known, and writes no dash", () => {
    const wrapper = mount(StationCard, {
      props: { row: station("X", { lat: null, lon: null, distance_km: null, bearing_deg: null, last_position_at: null }), now: NOW },
    });
    const rows = rowsOf(wrapper);
    for (const label of ["Position", "From us", "Speed", "Altitude", "Status", "Comment"]) expect(rows, label).not.toContain(label);
    expect(wrapper.findAll("dd").map((dd) => dd.text())).not.toContain("-");
  });
  it("says a speed and a course only for a station that moves; an altitude of zero that the station did send is kept", () => {
    const rows = (extra: Parameters<typeof station>[1]) => rowsOf(mount(StationCard, { props: { row: station("X", extra), now: NOW } }));
    expect(rows({ course_deg: 90, speed_kmh: 0 })).not.toContain("Speed");
    expect(rows({ course_deg: 90, speed_kmh: null })).not.toContain("Speed");
    expect(rows({ course_deg: 0, speed_kmh: 0, altitude_m: 0 })).toEqual(expect.arrayContaining(["Altitude"]));
    expect(rows({ course_deg: 0, speed_kmh: 0, altitude_m: 0 })).not.toContain("Speed");
    const text = (extra: Parameters<typeof station>[1]) => fieldsOf(mount(StationCard, { props: { row: station("X", extra), now: NOW } }))["Speed"];
    expect(text({ course_deg: 96, speed_kmh: 85 })).toBe("85 km/h, course 96° E");
    expect(text({ course_deg: null, speed_kmh: 85 })).toBe("85 km/h");
  });
  it("has no message settings: no path, suggested chip, or RF only on the card, whatever the station", () => {
    for (const r of [row, house, station("STORM", { kind: "object" })]) {
      const wrapper = mount(StationCard, { props: { row: r, now: NOW } });
      expect(wrapper.find(".use-suggested").exists()).toBe(false);
      expect(wrapper.find(".rfonly").exists()).toBe(false);
      expect(wrapper.find(".pathbox").exists()).toBe(false);
    }
  });

  it("has Forget as the trash can, named for the station, and says 'sure?' after the first press", () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW } });
    const button = wrapper.find(".card-foot .card-forget");
    expect(button.classes()).toContain("xbtn");
    expect(button.find("svg").exists()).toBe(true);
    expect(button.attributes("aria-label")).toBe("Forget OH2PU-9");
    expect(button.attributes("title")).toBe("Forget OH2PU-9");
    expect(wrapper.find(".card-foot .btn.forget").exists()).toBe(false);
  });

  it("has the envelope of 'message' beside the word on Message", () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW } });
    const button = wrapper.find(".card-foot .card-message");
    expect(button.find("svg.msgglyph").exists()).toBe(true);
    expect(button.text()).toBe("Message");
  });

  it("says 'Drag to move' on its head only when it can be moved", async () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW } });
    expect(wrapper.find(".card-head").attributes("title")).toBeUndefined();
    await wrapper.setProps({ movable: true });
    expect(wrapper.find(".card-head").attributes("title")).toContain("Drag to move");
  });

  it("forgets the station on the second click, not the first", async () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW } });
    const button = wrapper.find(".card-foot .card-forget");
    await button.trigger("click");
    expect(wrapper.emitted("forget")).toBeUndefined();
    expect(button.text()).toBe("sure?");
    await button.trigger("click");
    expect(wrapper.emitted("forget")).toEqual([["OH2PU-9"]]);
  });

  it("forgets its first click after 5 s, like the other buttons that ask twice", async () => {
    vi.useFakeTimers();
    const wrapper = mount(StationCard, { props: { row, now: NOW } });
    const button = wrapper.find(".card-foot .card-forget");
    await button.trigger("click");
    expect(button.text()).toBe("sure?");
    vi.advanceTimersByTime(4999);
    await wrapper.vm.$nextTick();
    expect(button.text()).toBe("sure?");
    vi.advanceTimersByTime(1);
    await wrapper.vm.$nextTick();
    expect(button.text()).toBe("");
    expect(button.attributes("aria-label")).toBe("Forget OH2PU-9");
    await button.trigger("click");
    expect(wrapper.emitted("forget")).toBeUndefined();
    expect(button.text()).toBe("sure?");
  });

  it("lets go of the first click when another station is shown", async () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW } });
    await wrapper.find(".card-foot .card-forget").trigger("click");
    await wrapper.setProps({ row: station("OH2RDG") });
    expect(wrapper.find(".card-foot .card-forget").text()).toBe("");
    await wrapper.find(".card-foot .card-forget").trigger("click");
    expect(wrapper.emitted("forget")).toBeUndefined();
  });

  it("has a green check mark beside the call of a station heard direct, named for a screen reader, and no Direct row or line about it", () => {
    const near = station("OH2PU-9", { last_direct_at: ago(300) });
    const wrapper = mount(StationCard, { props: { row: near, now: NOW } });
    const mark = wrapper.find(".card-call .direct-mark");
    expect(mark.exists()).toBe(true);
    expect(mark.attributes("title")).toBe("Heard direct");
    expect(mark.attributes("aria-label")).toBe("Heard direct");
    expect(wrapper.text()).not.toContain("not heard direct");
    expect(rowsOf(wrapper)).not.toContain("Direct");
    expect(cssRule(".direct-mark")).toMatch(/color:\s*var\(--ok\)/);
    for (const other of [
      station("X", { last_direct_at: null }),
      station("STORM", { kind: "object", last_direct_at: ago(60) }),
      station("OH2GBA", { is_me: true, last_direct_at: ago(60) }),
    ]) {
      expect(
        mount(StationCard, { props: { row: other, now: NOW } })
          .find(".direct-mark")
          .exists(),
      ).toBe(false);
    }
  });

  it("has the Message and Forget buttons of a station, in that order, with Message emitting the call", async () => {
    const wrapper = mount(StationCard, { props: { row: house, now: NOW } });
    expect(wrapper.findAll(".card-foot button").map((b) => b.text())).toEqual(["Message", ""]);
    await wrapper.find(".card-foot .btn.primary").trigger("click");
    expect(wrapper.emitted("message")).toEqual([["OH2DPN"]]);
  });

  it("has no Message button for a station that cannot do messages, and no gap where it was", async () => {
    const wrapper = mount(StationCard, { props: { row: station("OH2TRK", { can_message: false }), now: NOW } });
    expect(wrapper.findAll(".card-foot button").map((b) => b.text())).toEqual([""]);
    expect(wrapper.find(".card-foot .btn.primary").exists()).toBe(false);
    expect(wrapper.find(".card-foot .card-forget").exists()).toBe(true);
    await wrapper.setProps({ row: station("OH2TRK", { can_message: true }) });
    expect(wrapper.findAll(".card-foot button").map((b) => b.text())).toEqual(["Message", ""]);
  });

  it("offers to write to a station, and not to our own station or to an object", async () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW } });
    await wrapper.find(".card-foot .btn.primary").trigger("click");
    expect(wrapper.emitted("message")).toEqual([["OH2PU-9"]]);
    expect(
      mount(StationCard, { props: { row: station("STORM", { kind: "object", reported_by: "OH2XYZ" }), now: NOW } })
        .find(".card-foot .btn.primary")
        .exists(),
    ).toBe(false);
    expect(
      mount(StationCard, { props: { row: station("OH2GBA", { is_me: true }), now: NOW } })
        .find(".card-foot")
        .exists(),
    ).toBe(false);
  });

  const aging = (defaultMin: number): Aging => ({ defaultMin });

  it("has no timeout field: every station follows the fixed timeout", () => {
    for (const r of [row, station("OH2GBA", { is_me: true }), station("STORM", { kind: "object" })]) {
      const wrapper = mount(StationCard, { props: { row: r, now: NOW, aging: aging(1440) } });
      expect(wrapper.find(".timeoutbox, .timeout-input").exists()).toBe(false);
      expect(wrapper.text()).not.toContain("Hide from map after");
    }
  });

  it("has the bell of an alert at the end of the line of the call when one is set, with what it watches, and nothing without one", () => {
    const bell = mount(StationCard, { props: { row, now: NOW, alert: { on_air: false, within_km: 5, direct: true } } }).find(".card-call .alert-bell");
    expect(bell.attributes("title")).toBe("Alert when within 5 km, heard direct");
    expect(
      mount(StationCard, { props: { row, now: NOW } })
        .find(".alert-bell")
        .exists(),
    ).toBe(false);
  });

  it("has a QRZ link next to the call: the base call's page, in a new tab; for our own station too, not for an object or an item", () => {
    const link = mount(StationCard, { props: { row, now: NOW } }).find("a.qrz");
    expect(link.text()).toBe("QRZ");
    expect(link.attributes("href")).toBe("https://www.qrz.com/db/OH2PU");
    expect(link.attributes("target")).toBe("_blank");
    expect(link.attributes("rel")).toBe("noopener noreferrer");
    expect(
      mount(StationCard, { props: { row, now: NOW } })
        .find(".card-call")
        .text(),
    ).toBe("OH2PU-9QRZ");
    expect(
      mount(StationCard, { props: { row: station("OH2GBA-7", { is_me: true }), now: NOW } })
        .find("a.qrz")
        .attributes("href"),
    ).toBe("https://www.qrz.com/db/OH2GBA");
    for (const kind of ["object", "item"] as const) {
      expect(
        mount(StationCard, { props: { row: station("STORM", { kind }), now: NOW } })
          .find("a.qrz")
          .exists(),
      ).toBe(false);
    }
  });

  it("says when the last position is past the timeout", () => {
    const old = station("OH2OLD", { last_position_at: ago(7200) });
    expect(mount(StationCard, { props: { row: old, now: NOW, aging: aging(60) } }).text()).toContain("timed out");
    expect(mount(StationCard, { props: { row: old, now: NOW, aging: aging(0) } }).text()).not.toContain("timed out");
  });

  it("asks again for another station", async () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW } });
    await wrapper.find(".card-foot .card-forget").trigger("click");
    await wrapper.setProps({ row: station("OH2RDG") });
    expect(wrapper.find(".card-foot .card-forget").text()).toBe("");
  });

  it("does not offer to forget our own station, and closes", async () => {
    const wrapper = mount(StationCard, { props: { row: station("OH2GBA", { is_me: true }), now: NOW } });
    expect(wrapper.find(".card-foot").exists()).toBe(false);
    expect(wrapper.text()).toContain("our station");
    await wrapper.find("button[aria-label='Close']").trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("has a close button that is at least 32 px square, and a Details disclosure that has the way of the other disclosures", () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW } });
    expect(wrapper.find("button[aria-label='Close']").classes()).toContain("card-close");
    expect(cssRule(".xbtn")).toMatch(/min-width:\s*32px/);
    expect(cssRule(".xbtn")).toMatch(/min-height:\s*32px/);
    expect(wrapper.find("details").classes()).toContain("more");
  });

  it("has a pin beside the cross where the card can be moved: aria-pressed says whether it is on, a click asks to pin or unpin, the phone's sheet has none", async () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW, movable: true } });
    const pin = wrapper.find("button[aria-label='Pin card']");
    expect(pin.exists()).toBe(true);
    expect(pin.classes()).toContain("xbtn");
    expect(pin.attributes("aria-pressed")).toBe("false");
    expect(pin.attributes("title")).toBe("Pin card");
    const head = wrapper.find(".card-head").element;
    expect([...head.querySelectorAll("button")].map((b) => b.getAttribute("aria-label"))).toEqual(["Pin card", "Close"]);
    await pin.trigger("click");
    expect(wrapper.emitted("pin")).toHaveLength(1);
    expect(wrapper.emitted("close")).toBeUndefined();
    await wrapper.setProps({ pinned: true });
    expect(pin.attributes("aria-pressed")).toBe("true");
    expect(pin.attributes("title")).toBe("Unpin card");
    expect(
      mount(StationCard, { props: { row, now: NOW } })
        .find("button[aria-label='Pin card']")
        .exists(),
    ).toBe(false);
  });

  it("keeps the card clear of the zoom buttons of the map and, on a phone, leaves room above it for the marker", () => {
    expect(cssRule(".card")).toMatch(/max-height:\s*calc\(100% - 114px\)/);
    expect(cssRule(".size-phone .cardstack")).toMatch(/max-height:\s*88%/);
  });

  it("puts the weather panel at the top of a weather station's card, above the fields", () => {
    const wrapper = mount(StationCard, { props: { row: weatherStation("OH2MUI"), now: NOW } });
    const html = wrapper.html();
    expect(wrapper.find(".wx-temp").text()).toBe("10.0 °C");
    expect(html.indexOf("wx-temp")).toBeLessThan(html.indexOf("card-fields"));
    expect(html.indexOf("card-head")).toBeLessThan(html.indexOf("wx-temp"));
    expect(wrapper.find(".card-fields").exists()).toBe(true);
  });

  it("has the weather panel for the weather symbol alone, and for weather alone, and for no other station", () => {
    expect(
      mount(StationCard, { props: { row: station("A", { symbol_code: "_" }), now: NOW } })
        .find(".wx")
        .exists(),
    ).toBe(true);
    expect(
      mount(StationCard, { props: { row: station("A", { weather: weatherStation().weather }), now: NOW } })
        .find(".wx")
        .exists(),
    ).toBe(true);
    expect(
      mount(StationCard, { props: { row, now: NOW } })
        .find(".wx")
        .exists(),
    ).toBe(false);
  });

  it("asks for the series when it opens, gives the panel the answer, and asks again when the switch changes", async () => {
    const wrapper = mount(StationCard, { props: { row: weatherStation("OH2MUI"), now: NOW, weatherSeries: series("OH2MUI", 24, 12) } });
    expect(wrapper.emitted("weather")).toEqual([["OH2MUI", 24]]);
    expect(wrapper.findAll(".wx figure")).toHaveLength(4); // (the weather graphs; the bars of its packets are the fifth, under the facts)
    expect(wrapper.findAll("[data-packets] figure")).toHaveLength(1);
    expect(wrapper.emitted("packets")).toEqual([["OH2MUI"]]);
    await wrapper.findAll(".wx-span button")[1]?.trigger("click");
    expect(wrapper.emitted("weather")?.at(-1)).toEqual(["OH2MUI", 168]);
  });

  describe("an object or an item of ours", () => {
    const mine = station("LEADER", { kind: "object", reported_by: "OH2GBA", own: true, symbol_name: "Car" });
    const card = () => mount(StationCard, { props: { row: mine, now: NOW } });

    it("says it is ours, and by whom it is reported", () => {
      const text = card().text();
      expect(text).toContain("Car (ours)");
      expect(text).toContain("object, reported by OH2GBA");
    });

    it("has Edit and Kill in place of Message and Forget, and none of the fields of a station that is heard", () => {
      const wrapper = card();
      expect(wrapper.findAll(".card-foot button").map((b) => b.text())).toEqual(["Edit", "Kill"]);
      expect(wrapper.find(".forget").classes()).not.toContain("danger");
    });

    it("emits Edit with the name", async () => {
      const wrapper = card();
      await wrapper.find(".card-foot .primary").trigger("click");
      expect(wrapper.emitted("edit")).toEqual([["LEADER"]]);
    });

    it("kills on the second click, not the first, and forgets the first after 5 s", async () => {
      vi.useFakeTimers();
      const wrapper = card();
      const button = wrapper.find(".card-foot .forget");
      await button.trigger("click");
      expect(button.text()).toBe("Really kill?");
      expect(button.classes()).toContain("danger");
      expect(wrapper.emitted("kill")).toBeUndefined();
      vi.advanceTimersByTime(5001);
      await wrapper.vm.$nextTick();
      expect(button.text()).toBe("Kill");
      await button.trigger("click");
      await button.trigger("click");
      expect(wrapper.emitted("kill")).toEqual([["LEADER"]]);
      expect(wrapper.emitted("forget")).toBeUndefined();
    });
  });

  it("says who reported an object", () => {
    const text = mount(StationCard, { props: { row: station("STORM", { kind: "object", reported_by: "OH2XYZ" }), now: NOW } }).text();
    expect(text).toContain("object, reported by OH2XYZ");
  });
});
