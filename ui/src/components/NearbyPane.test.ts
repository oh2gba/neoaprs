import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import NearbyPane from "@/components/NearbyPane.vue";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { ago, station, table } from "@/test/fixtures";
import type { ExtensionValues, FrequencyValues } from "@/protocol/protocol";

const extensions: ExtensionValues = {
  phg: { power_w: 25, height_m: 12.2, gain_db: 5, direction_deg: null, range_km: 21.4 },
  range_km: null,
  dfs: null,
  df_bearing: null,
  area: null,
};
const voice: FrequencyValues = {
  mhz: 145.775,
  tone_hz: 118,
  tone_both: false,
  tone_off: false,
  dcs: null,
  tone_burst: false,
  narrow: false,
  offset_khz: -600,
  range_km: null,
  rx_mhz: null,
};

const rows = table(
  station("OH2GBA", { is_me: true, distance_km: null, bearing_deg: null, heard_via: [] }),
  station("OH2AAA", { distance_km: 8, heard_via: [["OH2RCH-2", 30]], heard_direct: 3, last_direct_at: ago(120) }),
  station("OH2RCH-2", { symbol_code: "#", distance_km: 12, bearing_deg: 90, heard_via: [], extensions, frequency: voice }),
  station("OH7JHF-1", { distance_km: 30, heard_via: [], gated: 12, igate: true }),
  station("R-HELSINKI", { kind: "object", reported_by: "OH2XYZ", distance_km: 20, heard_via: [], frequency: voice, can_message: false }),
);

function make(stations = rows, props: Record<string, unknown> = {}) {
  const daemon = fakeDaemon({ stations });
  const wrapper = mount(NearbyPane, { props: { selected: null, ...props }, global: withDaemon(daemon) });
  return { wrapper, daemon };
}
const section = (wrapper: ReturnType<typeof mount>, name: string) => wrapper.findAll("fieldset").find((s) => s.find("legend").text().startsWith(name));
const callsIn = (wrapper: ReturnType<typeof mount>, name: string) =>
  section(wrapper, name)
    ?.findAll("td.call")
    .map((c) => c.text());

beforeEach(() => localStorage.clear());

describe("NearbyPane", () => {
  it("has the four lists, each with its count, in the order digipeaters, voice frequencies, iGates, heard direct, and nothing of QRU", () => {
    const { wrapper } = make();
    expect(wrapper.findAll("fieldset > legend").map((h) => h.text().replace(/ ?i$/, ""))).toEqual([
      "Digipeaters 1",
      "Voice frequencies 2",
      "iGates 1",
      "Heard direct 1",
    ]);
  });

  it("puts every list in a group box with its title as the legend, like the groups of the Settings tab, and none of them is Local info (QRU), which is in the Objects tab", () => {
    const { wrapper } = make();
    expect(wrapper.findAll(".nearbypane > fieldset.nearby-section")).toHaveLength(4);
    expect(wrapper.find(".nearbypane .qru-ask, .nearbypane .objects-qru").exists()).toBe(false);
    expect(wrapper.find(".nearbypane > section").exists()).toBe(false);
  });

  it("has an (i) beside the Digipeaters heading that says what the range is, with a picture of a digipeater and its circle", async () => {
    const { wrapper } = make();
    const head = section(wrapper, "Digipeaters")?.find(".nearby-head");
    await head?.find("button.info-toggle").trigger("click");
    expect(head?.find(".info-text").text()).toContain("Stations inside its circle reach it; stations outside do not.");
    expect(head?.find("svg[data-picture='range']").exists()).toBe(true);
    const gates = section(wrapper, "iGates")?.find(".nearby-head");
    await gates?.find("button.info-toggle").trigger("click");
    expect(gates?.find(".info-text").text()).toContain("An iGate passes packets between the radio and the internet");
    expect(gates?.find("svg[data-picture='igate']").exists()).toBe(true);
    expect(section(wrapper, "Voice frequencies")?.find(".info-toggle").exists()).toBe(false);
  });

  it("lists the digipeater with what it repeated and the range it gave, and its distance and bearing", () => {
    const { wrapper } = make();
    const row = section(wrapper, "Digipeaters")?.find("tbody tr");
    expect(row?.find("td.call").text()).toBe("OH2RCH-2");
    expect(row?.find(".what").text()).toContain("30 packets repeated, PHG range 21 km");
    expect(row?.find(".num").text()).toBe("12");
    expect(row?.find(".bearing").attributes("title")).toBe("E, 90°");
  });

  it("lists the stations and objects that gave a voice frequency, nearest first, as the card words it, and who reported an object", () => {
    const { wrapper } = make();
    expect(callsIn(wrapper, "Voice")).toEqual(["OH2RCH-2", "R-HELSINKI"]);
    const object = section(wrapper, "Voice")?.findAll("tbody tr")[1];
    expect(object?.text()).toContain("145.775 MHz, tone 118 Hz, -600 kHz");
    expect(object?.text()).toContain("reported by OH2XYZ");
  });

  it("lists the iGate with the third-party packets it put on the air", () => {
    const { wrapper } = make();
    expect(callsIn(wrapper, "iGates")).toEqual(["OH7JHF-1"]);
    expect(section(wrapper, "iGates")?.text()).toContain("12 packets gated from the internet");
  });

  it("lists the station heard direct with when it was last heard direct", () => {
    const { wrapper } = make();
    expect(callsIn(wrapper, "Heard direct")).toEqual(["OH2AAA"]);
    expect(section(wrapper, "Heard direct")?.text()).toContain("last heard direct 2 min ago");
  });

  it("says none yet for a list that is empty, and has no table for it", () => {
    const { wrapper } = make(table(station("OH2GBA", { is_me: true, heard_via: [] })));
    for (const name of ["Digipeaters", "Voice", "iGates", "Heard direct"]) {
      expect(section(wrapper, name)?.find(".nearby-empty").text()).toBe("none yet");
      expect(section(wrapper, name)?.find("table").exists()).toBe(false);
    }
  });

  it("follows the stations as they are heard", async () => {
    const { wrapper, daemon } = make(table(station("OH2GBA", { is_me: true, heard_via: [] })));
    await tell(daemon, { stations: rows });
    expect(callsIn(wrapper, "Digipeaters")).toEqual(["OH2RCH-2"]);
  });

  it("selects the station of a clicked row like the Stations table does, with Ctrl adding a card, and Enter does the same", async () => {
    const { wrapper } = make();
    const row = section(wrapper, "iGates")?.find("tbody tr");
    await row?.trigger("click");
    await row?.trigger("click", { ctrlKey: true });
    await row?.trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("select")).toEqual([
      ["OH7JHF-1", false],
      ["OH7JHF-1", true],
      ["OH7JHF-1", false],
    ]);
  });

  it("marks the rows of the stations whose cards are open", () => {
    const { wrapper } = make(rows, { selected: "OH2RCH-2", others: ["R-HELSINKI"] });
    expect(wrapper.findAll("tr.selected").map((r) => r.attributes("data-call"))).toEqual(["OH2RCH-2", "OH2RCH-2", "R-HELSINKI"]);
  });

  it("lists a call that only repeated packets without a row to open: it is not a button", async () => {
    const { wrapper } = make(table(station("OH2AAA", { heard_via: [["OH2GHOST", 3]] })));
    const row = section(wrapper, "Digipeaters")?.find("tbody tr");
    expect(row?.text()).toContain("OH2GHOST");
    expect(row?.attributes("tabindex")).toBeUndefined();
    await row?.trigger("click");
    expect(wrapper.emitted("select")).toBeUndefined();
  });

  it("dims the row of a station past its timeout", () => {
    const old = table(station("OH7JHF-1", { gated: 1, last_position_at: ago(5 * 3600), last_heard: ago(5 * 3600), heard_via: [] }));
    const daemon = fakeDaemon({ stations: old, aging: { defaultMin: 180 } });
    const wrapper = mount(NearbyPane, { props: { selected: null }, global: withDaemon(daemon) });
    expect(wrapper.find("tr.timedout").exists()).toBe(true);
  });

  it("has no tickbox for the range: the circle is the selected digipeater's, on the map", () => {
    const { wrapper } = make(rows);
    expect(wrapper.findAll("input[type='checkbox']")).toHaveLength(0);
    expect(wrapper.text()).not.toContain("Show range");
    expect(wrapper.find(".nearby-ranges").exists()).toBe(false);
  });
});
