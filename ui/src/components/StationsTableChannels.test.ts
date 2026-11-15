import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { nextTick } from "vue";
import StationsTable from "@/components/StationsTable.vue";
import { cssRule } from "@/test/css";
import { fakeDaemon, withDaemon } from "@/test/context";
import type { RadioRow, StationRow } from "@/protocol/protocol";
import { ago, heardBy, radioRow, radiosTopic, station, table } from "@/test/fixtures";
import { STATIONS_TWO_RADIOS } from "@/lib/layout";
import { stubWidth } from "@/test/width";

const me = station("OH2GBA", { is_me: true, distance_km: null, bearing_deg: null, last_heard: ago(900), heard_rf: 0 });
const rf = station("OH2RF", { last_heard: ago(30), heard_rf: 4 });
const gated = station("OH2GATED", { last_heard: ago(60), heard_rf: 0, heard_rf_gated: 2, last_rf_at: null, last_rf_gated_at: ago(60) });
const net = station("OH2NET", {
  last_heard: ago(90),
  heard_rf: 0,
  heard_is: 3,
  last_rf_at: null,
  last_is_at: ago(90),
  position_via: "is",
  last_route: "",
  can_message: false,
});
const both = station("OH2BOTH", { last_heard: ago(20), heard_rf: 2, heard_is: 1, last_is_at: ago(20), last_rf_at: ago(100) });
const hfOnly = station("OH2HF", { last_heard: ago(40), heard_rf: 2, heard: heardBy([2, 2, ago(40)]) });
const fmAndHf = station("OH2FMHF", { last_heard: ago(10), heard_rf: 5, heard: heardBy([1, 3, ago(200)], [2, 2, ago(10)]) });
const object = station("LEADER", { kind: "object", own: true, last_heard: ago(200), heard_rf: 0 });

/** The station of the tests: the FM radio (radio 1) on, the HF radio (radio 2) off. */
const TODAY = () => radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { enabled: false, state: "stopped" }));
const make = (...rows: ReturnType<typeof station>[]) =>
  mount(StationsTable, { props: { selected: null }, global: withDaemon(fakeDaemon({ stations: table(...rows), radios: TODAY() })) });
const labels = (wrapper: ReturnType<typeof make>): [string, string][] =>
  wrapper.findAll("tbody tr[data-call]").map((tr): [string, string] => [
    tr.find(".callname").text(),
    tr
      .findAll(".via")
      .map((v) => v.text())
      .join(" · "),
  ]);

beforeEach(() => localStorage.clear());

describe("how a station was heard, in the Stations table", () => {
  it("is a small tag in its own column after the call of every row: RF, iGate, Internet or two tags, one for each way; none for our own station and our objects", () => {
    expect(labels(make(me, rf, gated, net, both, object))).toEqual([
      ["OH2GBA", ""],
      ["OH2BOTH", "RF · Internet"],
      ["OH2RF", "RF"],
      ["OH2GATED", "iGate"],
      ["OH2NET", "Internet"],
      ["LEADER", ""],
    ]);
  });

  it("has a tag HF for a station heard on the HF radio, beside RF when it was heard on the FM radio too, and RF alone for the rest as before", () => {
    expect(labels(make(rf, hfOnly, fmAndHf))).toEqual([
      ["OH2FMHF", "RF · HF"],
      ["OH2RF", "RF"],
      ["OH2HF", "HF"],
    ]);
    const tags = make(fmAndHf).findAll("tbody tr[data-call] .via");
    expect(tags.map((tag) => tag.attributes("title"))).toEqual(["Heard on the radio", "Heard on radio HF"]); // (plan section 6: what came by a radio that is now off carries its name, "Heard on radio {name}")
    expect(tags.map((tag) => tag.classes()[1])).toEqual(["tag-neutral", "tag-hf"]);
  });

  it("says in a title what the label means", () => {
    const wrapper = make(rf, net, both);
    const titles: Record<string, string | undefined> = {};
    for (const tr of wrapper.findAll("tbody tr[data-call]"))
      titles[tr.attributes("data-call") ?? ""] = tr
        .findAll(".via")
        .map((v) => v.attributes("title"))
        .join("; ");
    expect(titles).toEqual({
      OH2RF: "Heard on the radio",
      OH2NET: "Received over the internet (APRS-IS), not on the radio",
      OH2BOTH: "Heard on the radio; Received over the internet (APRS-IS), not on the radio",
    });
  });

  it("marks the row of a station known from the internet alone, and no other", () => {
    const wrapper = make(rf, net, both, gated);
    expect(wrapper.findAll("tbody tr.internetonly").map((tr) => tr.attributes("data-call"))).toEqual(["OH2NET"]);
  });

  it("keeps a row one line high and the tags in a column of their own after the call: they start at one place, whatever the length of the call", () => {
    const wrapper = make(rf, net, both);
    for (const tr of wrapper.findAll("tbody tr[data-call]")) {
      const cells = tr.findAll("td").map((td) => td.classes()[0]);
      expect(cells.slice(0, 3)).toEqual(["symbol", "mono", "heard"]);
      expect([...tr.get("td.call").element.children].map((c) => c.className.split(" ")[0])).toEqual(["callname", "alert-bell"]); // (the place of the bell of an alert, empty or not)
      expect(
        tr
          .get("td.heard .via")
          .classes()
          .some((c) => ["tag-neutral", "tag-hf", "tag-info", "tag-dummy"].includes(c)),
      ).toBe(true);
    }
    expect(wrapper.findAll("thead th").map((th) => th.text())).toContain("Heard on");
    expect(cssRule(".grid.stations td")).toMatch(/height:\s*30px/);
    expect(cssRule(".grid.stations td.call")).toMatch(/white-space:\s*nowrap/);
    expect(cssRule(".grid.stations td")).toMatch(/width:\s*1%/);
    expect(cssRule(".grid.stations td.heard")).toMatch(/width:\s*auto/);
    expect(cssRule(".size-phone .grid.stations td")).toMatch(/padding-left:\s*4px/); // (on a phone the extra column still leaves the actions in view: no cell is wider than it needs)
    expect(cssRule(".scroll")).toMatch(/overflow:\s*auto/); // (a table wider than the panel scrolls, a tag is never cut)
    expect(cssRule(".grid.stations tr.internetonly td.heard .via")).toMatch(/font-style:\s*italic/);
  });
});

describe("the tickbox heard on RF only", () => {
  const boxes = (wrapper: ReturnType<typeof make>): string[] =>
    wrapper.findAll("input[type='checkbox']").map((c) => c.element.parentElement?.textContent?.trim() ?? "");

  it("is not there while no station has been received over the internet", () => {
    expect(boxes(make(me, rf, gated))).toEqual(["hide timed out", "direct only"]);
  });

  it("is there from the first station received over the internet, next to the other two, and unticked", () => {
    const wrapper = make(me, rf, both);
    expect(boxes(wrapper)).toEqual(["hide timed out", "direct only", "heard on RF only"]);
    expect(wrapper.findAll<HTMLInputElement>("input[type='checkbox']")[2]?.element.checked).toBe(false);
    expect(wrapper.findAll("tbody tr[data-call]")).toHaveLength(3);
  });

  it("leaves out the stations known from the internet alone, not those also heard on the radio, an iGate's, ours or our objects", async () => {
    const wrapper = make(me, rf, gated, net, both, object);
    await wrapper.findAll("input[type='checkbox']")[2]?.setValue(true);
    expect(labels(wrapper).map(([call]) => call)).toEqual(["OH2GBA", "OH2BOTH", "OH2RF", "OH2GATED", "LEADER"]);
    expect(wrapper.find(".foot .footcount").text()).toBe("5 of 6 stations");
    await wrapper.findAll("input[type='checkbox']")[2]?.setValue(false);
    expect(labels(wrapper)).toHaveLength(6);
  });

  it("is remembered in this browser, like the others", async () => {
    const first = make(me, net, both);
    await first.findAll("input[type='checkbox']")[2]?.setValue(true);
    first.unmount();
    const again = make(me, net, both);
    expect(again.findAll<HTMLInputElement>("input[type='checkbox']")[2]?.element.checked).toBe(true);
    expect(labels(again).map(([call]) => call)).toEqual(["OH2GBA", "OH2BOTH"]);
  });

  it("has a title that says what it leaves out", () => {
    expect(make(net).find("label[title]").attributes("title")).toBe("Leave out the stations known only from the internet");
  });
});

describe("how a station was heard, with several radios", () => {
  const SIX: RadioRow[] = [
    radioRow(1, "kenwood-tnc2"),
    radioRow(2, "mercury"),
    radioRow(3, "kiss", { name: "Shack", number: 2 }),
    radioRow(4, "dummy-hf", { name: "20 m", number: 2 }),
    radioRow(5, "kantronics", { name: "Portable", number: 3 }),
    radioRow(6, "dummy", { name: "Bench", number: 4 }),
  ];
  const withRadios = (rows: RadioRow[], ...stations: StationRow[]) =>
    mount(StationsTable, {
      props: { selected: null },
      global: withDaemon(fakeDaemon({ stations: table(...stations), radios: radiosTopic(...rows) })),
    });
  const many = station("OH2SIX", {
    last_heard: ago(10),
    heard_rf: 9,
    heard_is: 1,
    last_is_at: ago(20),
    heard: {
      "1": { count: 2, last_at: ago(600) },
      "3": { count: 3, last_at: ago(60) },
      "4": { count: 1, last_at: ago(30) },
      "6": { count: 3, last_at: ago(3600) },
    },
  });

  it("names FM and HF by their short names while both are on, the station of the owner", () => {
    const wrapper = make(rf, hfOnly, fmAndHf);
    expect(labels(wrapper)).toEqual([
      ["OH2FMHF", "RF · HF"],
      ["OH2RF", "RF"],
      ["OH2HF", "HF"],
    ]);
    const both = mount(StationsTable, {
      props: { selected: null },
      global: withDaemon(fakeDaemon({ stations: table(rf, hfOnly, fmAndHf), radios: radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury")) })),
    });
    expect(labels(both)).toEqual([
      ["OH2FMHF", "FM · HF"],
      ["OH2RF", "FM"],
      ["OH2HF", "HF"],
    ]);
    expect(both.findAll("tr[data-call='OH2FMHF'] .via").map((tag) => [tag.attributes("title"), tag.classes()[1]])).toEqual([
      ["Heard on radio FM", "tag-neutral"],
      ["Heard on radio HF", "tag-hf"],
    ]);
  });

  it("shows the two radios that heard it last and +n, whose title lists the rest with their times; Internet apart", () => {
    const wrapper = withRadios(SIX, many);
    expect(labels(wrapper)).toEqual([["OH2SIX", "Shack · 20 m · +2 · Internet"]]);
    const tags = wrapper.findAll("tr[data-call='OH2SIX'] .via");
    expect(tags.map((tag) => tag.classes()[1])).toEqual(["tag-neutral", "tag-dummy", "tag-neutral", "tag-info"]);
    expect(tags[2]?.attributes("title")).toBe("FM: 10 min ago; Bench: 1 h ago"); // (a colon on every part once one needs it, as on the card)
  });

  describe("by the width of the table", () => {
    let width: ReturnType<typeof stubWidth> | undefined;
    afterEach(() => {
      width?.restore();
      width = undefined;
    });
    const eight = SIX.map((row, i) => ({ ...row, name: `Radio ${String.fromCharCode(65 + i)}12`.slice(0, 8) }));
    const heardByAll = station("OH2ALL", {
      heard_rf: 12,
      heard: Object.fromEntries(eight.map((row, i) => [String(row.id), { count: 2, last_at: ago(60 * (i + 1)) }])),
    });
    const shown = (wrapper: ReturnType<typeof withRadios>) => wrapper.findAll("tr[data-call='OH2ALL'] .via").map((tag) => tag.text());

    it("shows at six radios and names of eight letters one radio and +n in a table as narrow as a phone's (375 px), so that the row stays in the width", async () => {
      width = stubWidth(375);
      const wrapper = withRadios(eight, heardByAll);
      await nextTick();
      expect(shown(wrapper)).toEqual(["Radio A1", "+5"]);
      expect(wrapper.find("tr[data-call='OH2ALL'] .via:last-child").attributes("title")).toBe(
        "Radio B1: 2 min ago; Radio C1: 3 min ago; Radio D1: 4 min ago; Radio E1: 5 min ago; Radio F1: 6 min ago",
      );
    });

    it("shows two radios and +n from STATIONS_TWO_RADIOS on, and in a table not yet measured, and follows the width as it changes", async () => {
      width = stubWidth(STATIONS_TWO_RADIOS);
      const wrapper = withRadios(eight, heardByAll);
      await nextTick();
      expect(shown(wrapper)).toEqual(["Radio A1", "Radio B1", "+4"]);
      width.set(STATIONS_TWO_RADIOS - 1);
      await nextTick();
      expect(shown(wrapper)).toEqual(["Radio A1", "+5"]);
      width.restore();
      width = stubWidth(0);
      expect(shown(withRadios(eight, heardByAll))).toEqual(["Radio A1", "Radio B1", "+4"]);
    });

    it("keeps for a station with one radio on the tags of today at 375 px, a radio that is off among them", async () => {
      width = stubWidth(375);
      const wrapper = make(rf, hfOnly, fmAndHf);
      await nextTick();
      expect(labels(wrapper)).toEqual([
        ["OH2FMHF", "RF · HF"],
        ["OH2RF", "RF"],
        ["OH2HF", "HF"],
      ]);
    });
  });

  // (plan section 6, "Tags": a Dummy radio's tag and mark stay dashed, whatever its kind; with the Dummy HF radio alone its packets are the Dummy's, as the one radio on says them: "Dummy", where the HF tag of before stood beside it)
  it("says a Dummy HF radio's packets Dummy where it is the one radio on, and its name dashed beside FM", () => {
    const made = station("OH2DUM", {
      heard_rf: 0,
      heard_dummy: 3,
      last_rf_at: null,
      last_dummy_at: ago(30),
      heard: { "2": { count: 3, last_at: ago(30) } },
    });
    const fmOff = radioRow(1, "kenwood-tnc2", { enabled: false, state: "stopped" });
    const alone = mount(StationsTable, {
      props: { selected: null },
      global: withDaemon(fakeDaemon({ stations: table(made), radios: radiosTopic(fmOff, radioRow(2, "dummy-hf")) })),
    }).findAll("tr[data-call='OH2DUM'] .via");
    expect(alone.map((tag) => [tag.text(), tag.classes()[1], tag.attributes("title")])).toEqual([
      ["Dummy", "tag-dummy", "Made up by the Dummy radio, which is no real radio"],
    ]);
    const beside = withRadios([radioRow(1, "kenwood-tnc2"), radioRow(2, "dummy-hf")], made).findAll("tr[data-call='OH2DUM'] .via");
    expect(beside.map((tag) => [tag.text(), tag.classes()[1], tag.attributes("title")])).toEqual([["HF", "tag-dummy", "Heard on radio HF"]]);
  });

  it("says a radio the page does not know yet (the instant before the topic tells it) as the air, RF, with no name in its title", () => {
    const early = station("OH2NEW", { heard_rf: 2, heard: { "9": { count: 2, last_at: ago(30) } } });
    const tags = withRadios(SIX.slice(0, 2), early).findAll("tr[data-call='OH2NEW'] .via");
    expect(tags.map((tag) => [tag.text(), tag.classes()[1], tag.attributes("title")])).toEqual([["RF", "tag-neutral", "Heard on the radio"]]);
  });

  it("dims the tag of a removed radio, and keeps its name", () => {
    const removed = [SIX[0], SIX[1], { ...SIX[2], removed: true, enabled: false, state: "stopped" as const }];
    const old = station("OH2OLD", { heard_rf: 3, heard: { "3": { count: 3, last_at: ago(120) } } });
    const tags = withRadios(removed, old).findAll("tr[data-call='OH2OLD'] .via");
    expect(tags.map((tag) => [tag.text(), tag.classes()[1], tag.attributes("title")])).toEqual([["Shack", "tag-removed", "Heard on radio Shack"]]);
  });
});
