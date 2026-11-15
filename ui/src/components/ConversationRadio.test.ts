// The radio a conversation's header shows (the HF tag, FM and HF before Send, Route, and whether Send waits for the link) is the one the daemon says its messages go on: that of a message on its way, else the station's
// radio now, else for a call the book does not hold the main radio; the operator's choice in force comes before all, as it holds for a message on its way from its next attempt. Against a daemon that does not say, the rule of before (lib/radiosides.ts).
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import { shallowRef } from "vue";
import ConversationView from "@/components/ConversationView.vue";
import type { MessageRow, StationRow } from "@/protocol/protocol";
import { fakeDaemon, withDaemon, type Given } from "@/test/context";
import { configValues, message, station, status } from "@/test/fixtures";

beforeEach(() => localStorage.clear());

const BOTH = { "fm/enabled": "true", "hf/enabled": "true" };

function header(call: string, rows: StationRow[], thread: MessageRow[] = [], given: Given = {}) {
  const daemon = fakeDaemon({ config: configValues(BOTH), stations: shallowRef(new Map(rows.map((row) => [row.call, row]))), ...given });
  return mount(ConversationView, { props: { selected: call, narrow: false, thread }, global: withDaemon(daemon) });
}
const pressed = (wrapper: ReturnType<typeof header>) =>
  wrapper
    .findAll(".compose-radio button")
    .find((b) => b.attributes("aria-pressed") === "true")
    ?.text();
const hasRoute = (wrapper: ReturnType<typeof header>) => wrapper.findAll("button").some((b) => b.text() === "Route");
const tag = (wrapper: ReturnType<typeof header>) => wrapper.find(".convo-radio");

describe("the radio of a conversation", () => {
  it("is HF for a station FM heard long ago and HF lately, which the daemon messages over HF: no Route, HF pressed", () => {
    const wrapper = header("OH2LATE", [station("OH2LATE", { heard_fm: 30, heard_hf: 2, radio_now: 2 })]);
    expect([pressed(wrapper), hasRoute(wrapper)]).toEqual(["HF", false]);
  });

  it("is FM for a station heard on HF alone that the daemon messages over FM: Route, FM pressed", () => {
    const wrapper = header("OH2FAR", [station("OH2FAR", { heard_fm: 0, heard_hf: 3, radio_now: 1 })]);
    expect([pressed(wrapper), hasRoute(wrapper)]).toEqual(["FM", true]);
  });

  it("is the radio of a message on its way that keeps HF though the station is now messaged over FM", () => {
    const row = station("OH2RDG", { heard_fm: 3, heard_hf: 2, radio_now: 1 });
    const kept = message(4, { to_call: "OH2RDG", state: "sending", radio_now: 2 });
    expect([pressed(header("OH2RDG", [row], [kept])), hasRoute(header("OH2RDG", [row], [kept]))]).toEqual(["HF", false]);
    const done = message(4, { to_call: "OH2RDG", state: "acked", radio_now: null });
    expect([pressed(header("OH2RDG", [row], [done])), hasRoute(header("OH2RDG", [row], [done]))]).toEqual(["FM", true]);
  });

  it("follows the operator's press at once while a message is on its way, which takes the radio chosen from its next attempt", () => {
    const pressedFm = station("OH2RDG", { heard_fm: 3, heard_hf: 2, radio_choice: 1, radio_now: 1 });
    const sending = message(4, { to_call: "OH2RDG", state: "sending", radio: "hf", radio_now: 2 });
    const wrapper = header("OH2RDG", [pressedFm], [sending]);
    expect([pressed(wrapper), hasRoute(wrapper)]).toEqual(["FM", true]);
    const pressedHf = header("OH2RDG", [{ ...pressedFm, radio_choice: 2, radio_now: 2 }], [{ ...sending, radio: "fm", radio_now: 1 }]);
    expect([pressed(pressedHf), hasRoute(pressedHf)]).toEqual(["HF", false]);
  });

  it("is the main radio for a call nothing is known of: the HF tag and no Route while the main radio is HF", () => {
    const hf = header("OH2NEW", [], [], { status: status({ main_radio: 2 }) });
    expect([tag(hf).exists() && tag(hf).text(), hasRoute(hf)]).toEqual(["HF", false]);
    const fm = header("OH2NEW", [], [], { status: status({ main_radio: 1 }) });
    expect([tag(fm).exists(), hasRoute(fm)]).toEqual([false, true]);
  });

  it("waits for the link of the radio the daemon says, and Send says so", async () => {
    const wrapper = header("OH2LATE", [station("OH2LATE", { heard_fm: 30, heard_hf: 2, radio_now: 2 })], [], { connectedOn: (radio) => radio === "fm" });
    await wrapper.find("input.compose-text").setValue("Moi");
    expect(wrapper.find("button[type='submit']").attributes("disabled")).toBeDefined();
    const fm = header("OH2LATE", [station("OH2LATE", { heard_fm: 30, heard_hf: 2, radio_now: 1 })], [], { connectedOn: (radio) => radio === "fm" });
    await fm.find("input.compose-text").setValue("Moi");
    expect(fm.find("button[type='submit']").attributes("disabled")).toBeUndefined();
  });
});
