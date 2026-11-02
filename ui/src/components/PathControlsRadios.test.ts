// The controls that carry a path (Route of a conversation and of the station panel, Advanced of Ask around and of Local info) follow the radios: they are there while the FM radio is on, and for a station only while it is messaged on FM
// (one heard on the HF radio alone is messaged on HF, whose frames go direct).
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import { shallowRef } from "vue";
import ConversationView from "@/components/ConversationView.vue";
import NearbyAsk from "@/components/NearbyAsk.vue";
import ObjectsQru from "@/components/ObjectsQru.vue";
import StationPanel from "@/components/StationPanel.vue";
import { fakeDaemon, tell, withDaemon, type Given } from "@/test/context";
import { configValues, qruState, station } from "@/test/fixtures";

beforeEach(() => localStorage.clear());

const FM = { "fm/enabled": "true", "hf/enabled": "false" };
const BOTH = { "fm/enabled": "true", "hf/enabled": "true" };
const FM_OFF = { "fm/enabled": "false", "hf/enabled": "true" };

const fmHeard = station("OH2FM", { heard_fm: 3, heard_hf: 0 });
const bothHeard = station("OH2BOTH", { heard_fm: 3, heard_hf: 2 });
const hfHeard = station("OH2HF", { heard_fm: 0, heard_hf: 3, heard_rf: 3 });

const stations = (...rows: ReturnType<typeof station>[]) => new Map(rows.map((row) => [row.call, row]));

function conversation(values: Record<string, string>, call: string, rows = stations(fmHeard, bothHeard, hfHeard)) {
  const daemon = fakeDaemon({ config: configValues(values), stations: shallowRef(rows) });
  return mount(ConversationView, { props: { selected: call, narrow: false, thread: [] }, global: withDaemon(daemon) });
}
const hasRoute = (wrapper: ReturnType<typeof conversation>) => wrapper.findAll("button").some((b) => b.text() === "Route");

function panel(values: Record<string, string>, row: ReturnType<typeof station>) {
  const daemon = fakeDaemon({ config: configValues(values) });
  return mount(StationPanel, { props: { row, armed: false }, global: withDaemon(daemon) });
}
const hasPrefs = (wrapper: ReturnType<typeof panel>) => wrapper.findAll("legend").some((l) => l.text() === "Route");

const askPath = (given: Given) => mount(NearbyAsk, { global: withDaemon(fakeDaemon({ fallbackPath: "WIDE1-1", ...given })) });
const qruPath = (given: Given) => mount(ObjectsQru, { global: withDaemon(fakeDaemon({ fallbackPath: "WIDE1-1", qru: qruState({ asked: null }), ...given })) });
const hasAdvanced = (wrapper: ReturnType<typeof askPath>) => wrapper.findAll("details summary").some((s) => s.text() === "Advanced");

describe("Route in a conversation", () => {
  it("is there for a station heard on FM, or on both radios, or never heard, while the FM radio is on", () => {
    for (const values of [FM, BOTH]) {
      expect(
        [hasRoute(conversation(values, "OH2FM")), hasRoute(conversation(values, "OH2BOTH")), hasRoute(conversation(values, "OH2NEW"))],
        JSON.stringify(values),
      ).toEqual([true, true, true]);
    }
  });

  it("is not there for a station heard on the HF radio alone, which is messaged on HF", () => {
    expect(hasRoute(conversation(BOTH, "OH2HF"))).toBe(false);
  });

  it("is not there while the FM radio is off, whatever station it is", () => {
    for (const call of ["OH2FM", "OH2BOTH", "OH2HF", "OH2NEW"]) expect(hasRoute(conversation(FM_OFF, call)), call).toBe(false);
  });

  it("follows the radios as they are ticked", async () => {
    const daemon = fakeDaemon({ config: configValues(FM), stations: shallowRef(stations(fmHeard)) });
    const wrapper = mount(ConversationView, { props: { selected: "OH2FM", narrow: false, thread: [] }, global: withDaemon(daemon) });
    expect(hasRoute(wrapper)).toBe(true);
    await tell(daemon, { config: configValues(FM_OFF) });
    expect(hasRoute(wrapper)).toBe(false);
    await tell(daemon, { config: configValues(BOTH) });
    expect(hasRoute(wrapper)).toBe(true);
  });
});

describe("Route in the station panel", () => {
  it("is there for a station messaged on FM while the FM radio is on", () => {
    expect([hasPrefs(panel(FM, fmHeard)), hasPrefs(panel(BOTH, fmHeard)), hasPrefs(panel(BOTH, bothHeard))]).toEqual([true, true, true]);
  });

  it("is not there for a station heard on HF alone, nor while the FM radio is off", () => {
    expect([hasPrefs(panel(BOTH, hfHeard)), hasPrefs(panel(FM_OFF, fmHeard)), hasPrefs(panel(FM_OFF, hfHeard))]).toEqual([false, false, false]);
  });
});

describe("the path of Ask around and of Local info", () => {
  it("is there while the FM radio is on, with HF on or off", () => {
    for (const values of [FM, BOTH]) {
      expect(hasAdvanced(askPath({ config: configValues(values) })), "ask around").toBe(true);
      expect(hasAdvanced(qruPath({ config: configValues(values) })), "local info").toBe(true);
    }
  });

  it("is not there while the FM radio is off", () => {
    expect(hasAdvanced(askPath({ config: configValues(FM_OFF) }))).toBe(false);
    expect(hasAdvanced(qruPath({ config: configValues(FM_OFF) }))).toBe(false);
  });
});
