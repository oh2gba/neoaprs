// What the station panel of the Stations tab holds for each kind of row (StationPanel): its actions (Ask for weather only for a weather station), the operator's own query held to the daemon's rule, the station's traffic and
// its settings, saved as they are changed; our own station, our objects and another's object have only what applies to them. No line of text explains anything: a query that breaks the rule is marked and its Ask is off.
import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick, shallowReactive } from "vue";
import StationPanel from "@/components/StationPanel.vue";
import { useStationPrefs } from "@/composables/useStationPrefs";
import { fakeDaemon, withDaemon, type Given } from "@/test/context";
import { station } from "@/test/fixtures";
import type { Command, StationPref, StationRow } from "@/protocol/protocol";

let wrapper: VueWrapper;
let send: ReturnType<typeof vi.fn<(command: Command) => boolean>>;
let book: Map<string, StationPref>;
const make = (row: StationRow, over: Given = {}) => {
  send = vi.fn((_command: Command) => true);
  book = shallowReactive(new Map<string, StationPref>());
  const daemon = fakeDaemon({ send, home: { lat: 60.17, lon: 24.94 }, fallbackPath: "WIDE1-1,WIDE2-1", prefs: useStationPrefs(book, send), ...over });
  wrapper = mount(StationPanel, { props: { row, armed: false }, attachTo: document.body, global: withDaemon(daemon) });
  return wrapper;
};
const items = () => wrapper.findAll("[data-item]").map((b) => b.attributes("data-item"));
const legends = () => wrapper.findAll("legend").map((l) => l.text());
const tick = (name: string) => wrapper.find(`input[data-alert='${name}']`);
const query = () => wrapper.find("input[data-query='text']");
const ask = () => wrapper.find("button[data-query='ask']");

afterEach(() => {
  wrapper.unmount();
  document.body.replaceChildren();
});

describe("what the panel holds", () => {
  it("for a station heard: Message, the queries, its own query, Show, Copy, QRZ, Forget, its traffic, the route and the alert, and no note under the queries", () => {
    make(station("OH2RDG"));
    expect(items()).toEqual(["message", "ask_position", "ask_status", "ask_heard", "ask_trace", "show", "copy", "qrz", "forget"]);
    expect(query().exists()).toBe(true);
    expect(wrapper.text()).not.toContain("don't answer");
    expect(wrapper.find("[data-item='qrz']").attributes("href")).toContain("OH2RDG");
    expect(legends()).toEqual(["OH2RDG", "Traffic", "Route", "Alert me when OH2RDG…"]);
    expect(send).toHaveBeenCalledWith({ cmd: "station_traffic", call: "OH2RDG" });
  });

  it("for a weather station: Ask for weather after the other queries, its title saying that many do not answer it; none for any other station", () => {
    make(station("OH2MUI", { symbol_code: "_" }));
    expect(items().slice(0, 6)).toEqual(["message", "ask_position", "ask_status", "ask_heard", "ask_trace", "ask_weather"]);
    const wx = wrapper.find("[data-item='ask_weather']");
    expect(wx.text()).toBe("Ask for weather");
    expect(wx.attributes("title")).toContain("many stations don't answer it");
    wrapper.unmount();
    make(station("OH2RDG"));
    expect(items()).not.toContain("ask_weather");
  });

  it("for a station that takes no message: no Message, no queries, no own query and no route, but its traffic and the alert", () => {
    make(station("OH2NOM", { can_message: false }));
    expect(items()).toEqual(["show", "copy", "qrz", "forget"]);
    expect(query().exists()).toBe(false);
    expect(legends()).toEqual(["OH2NOM", "Traffic", "Alert me when OH2NOM…"]);
  });

  it("for our own station: Show, Copy and QRZ, and no settings", () => {
    make(station("OH2GBA", { is_me: true }));
    expect(items()).toEqual(["show", "copy", "qrz"]);
    expect(wrapper.find(".stationpanel-settings").exists()).toBe(false);
  });

  it("for an object of ours: Show and Copy; for another's object: Show, Copy and Forget; no traffic for either", () => {
    make(station("OH2OBJ", { kind: "object", can_message: false, own: true }));
    expect(items()).toEqual(["show", "copy"]);
    expect(wrapper.find(".stationpanel-settings").exists()).toBe(false);
    expect(wrapper.find(".stationpanel-traffic").exists()).toBe(false);
    wrapper.unmount();
    make(station("FOREIGN", { kind: "object", can_message: true, reported_by: "OH2RDG" }));
    expect(items()).toEqual(["show", "copy", "forget"]);
  });

  it("says Open its card for a station with no position", () => {
    make(station("OH2PU-9", { lat: null, lon: null }));
    expect(wrapper.find("[data-item='show']").text()).toBe("Open its card");
  });

  it("has the queries and its own query off with RX only, and Message on", () => {
    make(station("OH2RDG"), { receiveOnly: true });
    expect(wrapper.find("[data-item='ask_status']").attributes("disabled")).toBeDefined();
    expect(query().attributes("disabled")).toBeDefined();
    expect(ask().attributes("disabled")).toBeDefined();
    expect(wrapper.find("[data-item='message']").attributes("disabled")).toBeUndefined();
  });
});

describe("its own query", () => {
  it("is a box of at most 67 characters whose title names the other directed queries, with Ask off while it is empty", () => {
    make(station("OH2RDG"));
    expect(query().attributes("maxlength")).toBe("67");
    expect(query().attributes("title")).toContain("?APRSO");
    expect(query().attributes("title")).toContain("?PING?");
    expect(ask().attributes("disabled")).toBeDefined();
    expect(query().classes()).not.toContain("invalid");
  });

  it.each([
    ["APRSH OH2GBA-15", "A query begins with ? and says what it asks"],
    ["?", "A query begins with ? and says what it asks"],
    ["?" + "A".repeat(67), "At most 67 characters"],
    ["?APRS{1", "Plain ASCII only, without | ~ {"],
    ["?APRSÄ", "Plain ASCII only, without | ~ {"],
  ])("marks %s as wrong, says why only in its title, adds no line and keeps Ask off", async (text, why) => {
    make(station("OH2RDG"));
    const lines = wrapper.findAll(".stationpanel-body > *").length;
    await query().setValue(text);
    expect(query().classes()).toContain("invalid");
    expect(query().attributes("aria-invalid")).toBe("true");
    expect(query().attributes("title")).toBe(why);
    expect(ask().attributes("disabled")).toBeDefined();
    expect(wrapper.findAll(".stationpanel-body > *")).toHaveLength(lines);
    expect(wrapper.text()).not.toContain(why);
    await wrapper.find("form.stationpanel-query").trigger("submit");
    expect(wrapper.emitted("ask")).toBeUndefined();
  });

  it("sends a query upper-cased and trimmed, and empties the box", async () => {
    make(station("OH2RDG"));
    await query().setValue("  ?aprsh oh2gba-15 ");
    expect(query().classes()).not.toContain("invalid");
    expect(ask().attributes("disabled")).toBeUndefined();
    await ask().trigger("click");
    await wrapper.find("form.stationpanel-query").trigger("submit");
    expect(wrapper.emitted("ask")?.[0]).toEqual(["OH2RDG", "custom", "?APRSH OH2GBA-15"]);
    expect((query().element as HTMLInputElement).value).toBe("");
  });
});

describe("the settings in the panel", () => {
  it("send the station's path and RF only as they are changed", async () => {
    make(station("OH2RDG"));
    expect(wrapper.find(".path-line").text()).toBe("Automatic: WIDE1-1,WIDE2-1");
    const path = wrapper.find(".stationpanel-settings input[type='text']");
    await path.setValue("OH2RCH-2");
    await path.trigger("change");
    expect(send).toHaveBeenCalledWith({ cmd: "set_station_path", call: "OH2RDG", path: "OH2RCH-2" });
    await wrapper.find(".rfonly input").setValue(true);
    expect(send).toHaveBeenCalledWith({ cmd: "set_station_rf_only", call: "OH2RDG", on: true });
  });

  it("send the whole alert as a tickbox is ticked or cleared, and the distance once it is in the daemon's range, which is marked and not written out", async () => {
    make(station("OH2RDG"));
    expect(wrapper.text()).not.toMatch(/1 to 1000/);
    await tick("on_air").setValue(true);
    expect(send).toHaveBeenLastCalledWith({ cmd: "set_station_alert", call: "OH2RDG", on_air: true, within_km: null, direct: false });
    await tick("within").setValue(true);
    expect(send).toHaveBeenLastCalledWith({ cmd: "set_station_alert", call: "OH2RDG", on_air: true, within_km: 10, direct: false });
    const km = wrapper.find("input[type='number']");
    send.mockClear();
    for (const bad of [0, 1001, 2.5]) {
      await km.setValue(bad);
      await km.trigger("change");
      expect(km.attributes("aria-invalid"), String(bad)).toBe("true");
      expect(km.classes(), String(bad)).toContain("invalid");
    }
    expect(send).not.toHaveBeenCalled();
    expect(wrapper.find(".alertbox-note").exists()).toBe(false);
    await km.setValue(25);
    await km.trigger("change");
    expect(km.classes()).not.toContain("invalid");
    expect(send).toHaveBeenLastCalledWith({ cmd: "set_station_alert", call: "OH2RDG", on_air: true, within_km: 25, direct: false });
  });

  it("say only that our position is missing when it is", () => {
    make(station("OH2RDG"), { home: null });
    expect(wrapper.find(".alertbox-note").text()).toBe("Needs your position (Settings)");
  });

  it("show the alert the station has, and take in a change of it from the daemon", async () => {
    make(station("OH2RDG"));
    expect((tick("on_air").element as HTMLInputElement).checked).toBe(false);
    book.set("OH2RDG", { path: null, rf_only: false, alert: { on_air: false, within_km: 5, direct: true } });
    await nextTick();
    expect([tick("on_air"), tick("within"), tick("direct")].map((t) => (t.element as HTMLInputElement).checked)).toEqual([false, true, true]);
    expect((wrapper.find("input[type='number']").element as HTMLInputElement).value).toBe("5");
  });
});
