import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import StationCard from "@/components/StationCard.vue";
import type { Aging } from "@/lib/aging";
import type { Attempts } from "@/lib/attempts";
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

  it("has dashes where no route is known", () => {
    const none = station("X", { last_route: "", heard_via: [], best_route: "", suggested_path: null });
    const fields = Object.fromEntries(
      mount(StationCard, { props: { row: none, now: NOW } })
        .findAll("dt")
        .map((dt) => [dt.text(), dt.element.nextElementSibling?.textContent?.trim()]),
    );
    expect([fields["Route"], fields["Heard"], fields["Best route"]]).toEqual(["-", "-", "-"]);
  });

  it("puts the suggested path on the chip beside the path field: saved at once, none when there is no suggestion", async () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW, fallbackPath: "WIDE1-1" } });
    await wrapper.find(".card-path .use-suggested").trigger("click");
    expect(wrapper.emitted("path")).toEqual([["OH2PU-9", "OH2RCH-2"]]);
    const unknown = mount(StationCard, { props: { row: station("OH2PU-9", { suggested_path: null }), now: NOW } });
    expect(unknown.find(".card-path .use-suggested").exists()).toBe(false);
  });

  it("shows a dash for what is not known", () => {
    const text = mount(StationCard, {
      props: { row: station("X", { course_deg: null, speed_kmh: null, altitude_m: null, distance_km: null, last_status: "" }), now: NOW },
    }).text();
    expect(text).toContain("Course-");
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
    expect(fieldsOf(mount(StationCard, { props: { row: station("STORM", { kind: "object" }), now: NOW } }))["Direct"]).toBe("-");
    expect(fieldsOf(mount(StationCard, { props: { row: station("OH2GBA", { is_me: true }), now: NOW } }))["Direct"]).toBe("-");
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

  it("shows the path its messages go by and says when it is saved or cleared; not for our own station or an object", async () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW, paths: new Map([["OH2PU-9", "OH2RCH-2"]]), fallbackPath: "WIDE1-1" } });
    expect(wrapper.find<HTMLInputElement>(".card-path input").element.value).toBe("OH2RCH-2");
    await wrapper.find(".card-path input").setValue("WIDE2-1");
    expect(wrapper.emitted("path")).toEqual([["OH2PU-9", "WIDE2-1"]]);
    await wrapper.find(".card-path .use-default").trigger("click");
    expect(wrapper.emitted("clearPath")).toEqual([["OH2PU-9"]]);
    expect(
      mount(StationCard, { props: { row, now: NOW, fallbackPath: "WIDE1-1" } })
        .find(".card-path")
        .text(),
    ).toContain("(default)");
    expect(
      mount(StationCard, { props: { row: station("OH2GBA", { is_me: true }), now: NOW } })
        .find(".card-path")
        .exists(),
    ).toBe(false);
    const storm = mount(StationCard, { props: { row: station("STORM", { kind: "object" }), now: NOW } });
    expect(storm.find(".card-path").text()).not.toContain("Path");
    expect(storm.find(".card-path").text()).toContain("Off map after");
  });

  const aging = (defaultMin: number, own: [string, number][] = []): Aging => ({ timeouts: new Map(own), defaultMin });

  it("has the timeout beside the path: saved when changed, cleared when emptied or by the x; not for our own station", async () => {
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
  });

  const attempts = (defaultCount: number, own: [string, number][] = []): Attempts => ({ own: new Map(own), defaultCount });

  it("has the attempts beside the path and the timeout, with the setting as the placeholder, for every station but our own", async () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW, attempts: attempts(6) } });
    const input = wrapper.find<HTMLInputElement>(".card-path .attempts-input");
    expect(input.attributes("placeholder")).toBe("(default: 6)");
    await input.setValue("2");
    expect(wrapper.emitted("setAttempts")).toEqual([["OH2PU-9", 2]]);
    const own = mount(StationCard, { props: { row, now: NOW, attempts: attempts(6, [["OH2PU-9", 1]]) } });
    expect(own.find<HTMLInputElement>(".attempts-input").element.value).toBe("1");
    await own.find(".attemptsbox .use-default").trigger("click");
    expect(own.emitted("clearAttempts")).toEqual([["OH2PU-9"]]);
    const labels = wrapper.findAll(".card-path label").map((l) => l.text());
    expect(labels).toEqual(["Path", "RF only", "Off map after", "Attempts"]);
    expect(
      mount(StationCard, { props: { row: station("STORM", { kind: "object" }), now: NOW } })
        .find(".card-path .attempts-input")
        .exists(),
    ).toBe(true);
    expect(
      mount(StationCard, { props: { row: station("OH2GBA", { is_me: true }), now: NOW } })
        .find(".attempts-input")
        .exists(),
    ).toBe(false);
  });

  it("has the RF only tickbox beside the path on the card of a station that can be messaged, not on an object's", async () => {
    const wrapper = mount(StationCard, { props: { row, now: NOW, rfOnly: new Set(["OH2PU-9"]) } });
    const box = wrapper.find<HTMLInputElement>(".card-path .pathbox .rfonly input");
    expect(box.element.checked).toBe(true);
    await box.setValue(false);
    expect(wrapper.emitted("setRfOnly")).toEqual([["OH2PU-9", false]]);
    expect(
      mount(StationCard, { props: { row: station("STORM", { kind: "object" }), now: NOW } })
        .find(".rfonly")
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

  it("says who reported an object", () => {
    const text = mount(StationCard, { props: { row: station("STORM", { kind: "object", reported_by: "OH2XYZ" }), now: NOW } }).text();
    expect(text).toContain("object, reported by OH2XYZ");
  });
});
