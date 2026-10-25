import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import BearingArrow from "@/components/BearingArrow.vue";
import StationCard from "@/components/StationCard.vue";
import { NOW, station } from "@/test/fixtures";

const phg = (direction_deg: number | null) => ({
  phg: { power_w: 25, height_m: 6.1, gain_db: 3, direction_deg, range_km: 12.8 },
  range_km: null,
  dfs: null,
  df_bearing: null,
  area: null,
});
const fieldsOf = (wrapper: ReturnType<typeof mount>) =>
  Object.fromEntries(wrapper.findAll("dt").map((dt) => [dt.text(), dt.element.nextElementSibling as HTMLElement]));

describe("the device on the card", () => {
  it("is one line, Device, when the device list knows what the station runs", () => {
    const fields = fieldsOf(mount(StationCard, { props: { row: station("OH2PU-9", { device: "Kenwood TH-D74" }), now: NOW } }));
    expect(fields["Device"]?.textContent?.trim()).toBe("Kenwood TH-D74");
  });

  it("is left out when unknown, with no empty row", () => {
    const wrapper = mount(StationCard, { props: { row: station("OH2PU-9", { device: "" }), now: NOW } });
    expect(wrapper.findAll("dt").map((dt) => dt.text())).not.toContain("Device");
  });
});

describe("the antenna direction on the card", () => {
  it("is the arrow of the Stations table turned to the direction, the words as its hover title", () => {
    const wrapper = mount(StationCard, { props: { row: station("OH2PU-9", { extensions: phg(45) }), now: NOW } });
    const dd = fieldsOf(wrapper)["PHG"];
    expect(dd?.textContent?.trim()).toBe("25 W, 6 m, 3 dB, range 13 km");
    expect(wrapper.findComponent(BearingArrow).props("deg")).toBe(45);
    expect(wrapper.find(".antenna svg.arrow").attributes("style")).toContain("rotate(45deg)");
    expect(wrapper.find(".antenna").attributes("title")).toBe("NE, 45°");
  });

  it("is a small circle for an omni antenna, named omni", () => {
    const wrapper = mount(StationCard, { props: { row: station("OH2PU-9", { extensions: phg(null) }), now: NOW } });
    expect(wrapper.find(".antenna svg circle").exists()).toBe(true);
    expect(wrapper.find(".antenna svg path").exists()).toBe(false);
    expect(wrapper.find(".antenna").attributes("title")).toBe("omni");
  });

  it("is left out for a position with no PHG", () => {
    expect(
      mount(StationCard, { props: { row: station("OH2PU-9"), now: NOW } })
        .find(".antenna")
        .exists(),
    ).toBe(false);
  });
});

describe("the packets on the card", () => {
  it("are the total and those of the last hour", () => {
    const fields = fieldsOf(mount(StationCard, { props: { row: station("OH2PU-9", { packets: 312, packets_hour: 14 }), now: NOW } }));
    expect(fields["Packets"]?.textContent?.trim()).toBe("312 · 14 in the last hour");
  });

  it("are only the total for our own station and for an object of ours, which are not heard", () => {
    const own = fieldsOf(mount(StationCard, { props: { row: station("LEADER", { kind: "object", own: true, packets: 5 }), now: NOW } }));
    expect(own["Packets"]?.textContent?.trim()).toBe("5");
    const me = fieldsOf(mount(StationCard, { props: { row: station("OH2GBA-7", { is_me: true, packets: 0 }), now: NOW } }));
    expect(me["Packets"]?.textContent?.trim()).toBe("0");
  });
});

describe("the voice frequency on the card", () => {
  it("is one line with the tone, the offset and the range the station sent", () => {
    const frequency = {
      mhz: 145.775,
      tone_hz: 118,
      tone_both: false,
      tone_off: false,
      dcs: null,
      tone_burst: false,
      narrow: false,
      offset_khz: -600,
      range_km: 40.2,
      rx_mhz: null,
    };
    const fields = fieldsOf(mount(StationCard, { props: { row: station("OH2PU-9", { frequency }), now: NOW } }));
    expect(fields["Frequency"]?.textContent?.trim()).toBe("145.775 MHz, tone 118 Hz, -600 kHz, range 40 km");
  });

  it("is left out when the station gave none", () => {
    expect(
      mount(StationCard, { props: { row: station("OH2PU-9"), now: NOW } })
        .findAll("dt")
        .map((dt) => dt.text()),
    ).not.toContain("Frequency");
  });
});

describe("the storm data and the sign in the details", () => {
  it("tell a storm object in words and a signpost by what it shows", () => {
    const storm = {
      storm_type: "HC",
      wind_kmh: 277.8,
      gust_kmh: null,
      pressure_hpa: 980,
      hurricane_radius_km: null,
      storm_radius_km: null,
      gale_radius_km: null,
    } as const;
    const fields = fieldsOf(mount(StationCard, { props: { row: station("BRENDA", { kind: "object", storm }), now: NOW } }));
    expect(fields["Storm"]?.textContent?.trim()).toBe("Hurricane, wind 278 km/h, pressure 980 hPa");
    const sign = fieldsOf(mount(StationCard, { props: { row: station("I91 3N", { kind: "item", sign: "55" }), now: NOW } }));
    expect(sign["Sign"]?.textContent?.trim()).toBe("55");
    expect(Object.keys(fieldsOf(mount(StationCard, { props: { row: station("OH2PU-9"), now: NOW } })))).not.toEqual(expect.arrayContaining(["Storm", "Sign"]));
  });
});
