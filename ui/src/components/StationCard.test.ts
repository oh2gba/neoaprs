import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import StationCard from "@/components/StationCard.vue";
import type { Aging } from "@/lib/aging";
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
  it("shows every field of the row", () => {
    const text = mount(StationCard, { props: { row, now: NOW } }).text();
    for (const wanted of [
      "OH2PU-9",
      "Car",
      "60.19908 N 24.65007 E",
      "16 km, 282° WNW",
      "356°",
      "42 km/h",
      "31 m",
      "2 min ago",
      "10 min ago",
      "OH2RCH-2*,WIDE2-1",
      "on air",
      "QRV D-STAR",
      "19",
    ]) {
      expect(text, wanted).toContain(wanted);
    }
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
    expect(fields.PHG).toBe("25 W, 6 m, 3 dB, 90°, range 13 km");
    expect(fields.Range).toBe("81 km");
    expect(fields.Locator).toBe("IO91sx, 51.97917 N 0.45833 W");
    expect(fields.Telemetry).toBe("#5: Battery 1034.8 v/100");
    expect(fields.Bits).toBe("Camra on");
  });

  it("says how its packets reach us: the latest route, the counts and the best route with the path to send by", () => {
    const heard = station("OH2PU-9", {
      last_route: "via OH2RCH-1 → OH2RCH-3",
      heard_direct: 12,
      heard_via: [
        ["OH2RCH-2", 30],
        ["OH2RCH-3", 4],
      ],
      heard_gated: 2,
      best_route: "via OH2RCH-2",
      suggested_path: "OH2RCH-2",
    });
    const wrapper = mount(StationCard, { props: { row: heard, now: NOW } });
    const fields = Object.fromEntries(wrapper.findAll("dt").map((dt) => [dt.text(), dt.element.nextElementSibling?.textContent?.trim()]));
    expect(fields["Route"]).toBe("via OH2RCH-1 → OH2RCH-3");
    expect(fields["Heard"]).toBe("12 direct, 30 via OH2RCH-2, 4 via OH2RCH-3, 2 from the internet");
    expect(fields["Best route"]).toBe("via OH2RCH-2; send by OH2RCH-2");
  });

  it("leaves out the rows of a route that is not known", () => {
    const none = station("X", { last_route: "", heard_via: [], best_route: "", suggested_path: null, last_path: [] });
    const fields = fieldsOf(mount(StationCard, { props: { row: none, now: NOW } }));
    for (const label of ["Path", "Route", "Heard", "Best route"]) expect(fields, label).not.toHaveProperty(label);
    expect(fields).toHaveProperty("Direct");
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

  it("has the rows of a moving station: course, speed and altitude, status and comment, in the order of the card", () => {
    expect(rowsOf(mount(StationCard, { props: { row, now: NOW } }))).toEqual([
      "Symbol",
      "Position",
      "From us",
      "Course",
      "Speed",
      "Altitude",
      "Last heard",
      "Last position",
      "First heard",
      "Path",
      "Route",
      "Heard",
      "Direct",
      "Best route",
      "Status",
      "Comment",
      "Packets",
    ]);
  });

  it("leaves out the rows with nothing to say: no course, speed, altitude, status or comment for a house", () => {
    expect(rowsOf(mount(StationCard, { props: { row: house, now: NOW } }))).toEqual([
      "Symbol",
      "Position",
      "From us",
      "Last heard",
      "Last position",
      "First heard",
      "Path",
      "Route",
      "Heard",
      "Direct",
      "Best route",
      "Packets",
    ]);
  });

  it("leaves out what is not known, and writes no dash", () => {
    const wrapper = mount(StationCard, {
      props: { row: station("X", { lat: null, lon: null, distance_km: null, bearing_deg: null, last_position_at: null }), now: NOW },
    });
    const rows = rowsOf(wrapper);
    for (const label of ["Position", "From us", "Last position", "Course", "Speed", "Altitude", "Status", "Comment"]) expect(rows, label).not.toContain(label);
    expect(wrapper.findAll("dd").map((dd) => dd.text())).not.toContain("-");
  });

  it("keeps a course, a speed or an altitude of zero: the station gave it", () => {
    const rows = rowsOf(mount(StationCard, { props: { row: station("X", { course_deg: 0, speed_kmh: 0, altitude_m: 0 }), now: NOW } }));
    expect(rows).toEqual(expect.arrayContaining(["Course", "Speed", "Altitude"]));
  });

  it("has no message settings: no path, suggested chip, or RF only on the card, whatever the station", () => {
    for (const r of [row, house, station("STORM", { kind: "object" })]) {
      const wrapper = mount(StationCard, { props: { row: r, now: NOW } });
      expect(wrapper.find(".use-suggested").exists()).toBe(false);
      expect(wrapper.find(".rfonly").exists()).toBe(false);
      expect(wrapper.find(".pathbox:not(.timeoutbox)").exists()).toBe(false);
      expect(wrapper.findAll(".card-path label").map((l) => l.text())).toEqual(["Off map after"]);
    }
  });

  it("forgets the station on the second click, not the first", async () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW } });
    const button = wrapper.find(".card-foot .forget");
    await button.trigger("click");
    expect(wrapper.emitted("forget")).toBeUndefined();
    expect(button.text()).toBe("Really forget?");
    await button.trigger("click");
    expect(wrapper.emitted("forget")).toEqual([["OH2PU-9"]]);
  });

  it("forgets its first click after 5 s, like the other buttons that ask twice", async () => {
    vi.useFakeTimers();
    const wrapper = mount(StationCard, { props: { row, now: NOW } });
    const button = wrapper.find(".card-foot .forget");
    await button.trigger("click");
    expect(button.text()).toBe("Really forget?");
    vi.advanceTimersByTime(4999);
    await wrapper.vm.$nextTick();
    expect(button.text()).toBe("Really forget?");
    vi.advanceTimersByTime(1);
    await wrapper.vm.$nextTick();
    expect(button.text()).toBe("Forget");
    await button.trigger("click");
    expect(wrapper.emitted("forget")).toBeUndefined();
    expect(button.text()).toBe("Really forget?");
  });

  it("lets go of the first click when another station is shown", async () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW } });
    await wrapper.find(".card-foot .forget").trigger("click");
    await wrapper.setProps({ row: station("OH2RDG") });
    expect(wrapper.find(".card-foot .forget").text()).toBe("Forget");
    await wrapper.find(".card-foot .forget").trigger("click");
    expect(wrapper.emitted("forget")).toBeUndefined();
  });

  it("says when it was last heard direct and how much of what it sent came direct", () => {
    const near = station("OH2PU-9", { last_direct_at: ago(300), heard_direct: 2, heard_via: [["OH2RCH-2", 3]], heard_gated: 0 });
    expect(fieldsOf(mount(StationCard, { props: { row: near, now: NOW } }))["Direct"]).toBe("heard direct 5 min ago, 40 % of its packets");
    expect(fieldsOf(mount(StationCard, { props: { row: station("X", { last_direct_at: null }), now: NOW } }))["Direct"]).toBe("not heard direct");
    expect(fieldsOf(mount(StationCard, { props: { row: station("STORM", { kind: "object" }), now: NOW } }))).not.toHaveProperty("Direct");
    expect(fieldsOf(mount(StationCard, { props: { row: station("OH2GBA", { is_me: true }), now: NOW } }))).not.toHaveProperty("Direct");
  });

  it("has the Message and Forget buttons of a station, in that order, with Message emitting the call", async () => {
    const wrapper = mount(StationCard, { props: { row: house, now: NOW } });
    expect(wrapper.findAll(".card-foot button").map((b) => b.text())).toEqual(["Message", "Forget"]);
    await wrapper.find(".card-foot .btn.primary").trigger("click");
    expect(wrapper.emitted("message")).toEqual([["OH2DPN"]]);
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

  const aging = (defaultMin: number, own: [string, number][] = []): Aging => ({ timeouts: new Map(own), defaultMin });

  it("has the station's own timeout: saved when changed, cleared when emptied or by the x; for an object too, not for our own station", async () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW, aging: aging(1440) } });
    const input = wrapper.find<HTMLInputElement>(".card-path .timeout-input");
    expect(input.attributes("placeholder")).toBe("(default: 1 d)");
    await input.setValue("90");
    expect(wrapper.emitted("timeout")).toEqual([["OH2PU-9", 90]]);
    const own = mount(StationCard, { props: { row, now: NOW, aging: aging(1440, [["OH2PU-9", 0]]) } });
    expect(own.find<HTMLInputElement>(".timeout-input").element.value).toBe("never");
    await own.find(".timeoutbox .use-default").trigger("click");
    expect(own.emitted("clearTimeout")).toEqual([["OH2PU-9"]]);
    await own.find(".timeout-input").setValue("");
    expect(own.emitted("clearTimeout")).toHaveLength(2);
    expect(
      mount(StationCard, { props: { row: station("OH2GBA", { is_me: true }), now: NOW } })
        .find(".timeout-input")
        .exists(),
    ).toBe(false);
    expect(
      mount(StationCard, { props: { row: station("STORM", { kind: "object" }), now: NOW } })
        .find(".timeout-input")
        .exists(),
    ).toBe(true);
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
    await wrapper.find(".card-foot .forget").trigger("click");
    await wrapper.setProps({ row: station("OH2RDG") });
    expect(wrapper.find(".card-foot .forget").text()).toBe("Forget");
  });

  it("does not offer to forget our own station, and closes", async () => {
    const wrapper = mount(StationCard, { props: { row: station("OH2GBA", { is_me: true }), now: NOW } });
    expect(wrapper.find(".card-foot").exists()).toBe(false);
    expect(wrapper.text()).toContain("our station");
    await wrapper.find("button[aria-label='Close']").trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);
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
    expect(wrapper.findAll("figure")).toHaveLength(4);
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
      expect(wrapper.find(".card-path").exists()).toBe(false);
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
