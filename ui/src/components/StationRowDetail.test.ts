// What the field under a row of the Stations table holds for each kind of row (StationRowDetail): the actions of the menu but "Alert me when…", whose choices are in the field itself, and the settings, saved as they are changed;
// our own station, our objects and another's object have only what applies to them.
import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick, shallowReactive } from "vue";
import StationRowDetail from "@/components/StationRowDetail.vue";
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
  wrapper = mount(StationRowDetail, { props: { row, armed: false }, attachTo: document.body, global: withDaemon(daemon) });
  return wrapper;
};
const items = () => wrapper.findAll("[data-item]").map((b) => b.attributes("data-item"));
const legends = () => wrapper.findAll("legend").map((l) => l.text());
const tick = (name: string) => wrapper.find(`input[data-alert='${name}']`);

afterEach(() => {
  wrapper.unmount();
  document.body.replaceChildren();
});

describe("what the field holds", () => {
  it("for a station heard: Message, the queries with their note, Show, Copy, QRZ, Forget, the route and the alert", () => {
    make(station("OH2RDG"));
    expect(items()).toEqual(["message", "ask_position", "ask_status", "ask_heard", "ask_trace", "show", "copy", "qrz", "forget"]);
    expect(wrapper.find(".stationfield-note").text()).toBe("Many stations don't answer queries.");
    expect(wrapper.find("[data-item='qrz']").attributes("href")).toContain("OH2RDG");
    expect(legends()).toEqual(["Route", "Alert me when OH2RDG…"]);
  });

  it("for a station that takes no message: no Message, no queries and no route, but the alert", () => {
    make(station("OH2NOM", { can_message: false }));
    expect(items()).toEqual(["show", "copy", "qrz", "forget"]);
    expect(wrapper.find(".stationfield-note").exists()).toBe(false);
    expect(legends()).toEqual(["Alert me when OH2NOM…"]);
  });

  it("for our own station: Show, Copy and QRZ, and no settings", () => {
    make(station("OH2GBA", { is_me: true }));
    expect(items()).toEqual(["show", "copy", "qrz"]);
    expect(wrapper.find(".stationfield-settings").exists()).toBe(false);
  });

  it("for an object of ours: Show and Copy; for another's object: Show, Copy and Forget", () => {
    make(station("OH2OBJ", { kind: "object", can_message: false, own: true }));
    expect(items()).toEqual(["show", "copy"]);
    expect(wrapper.find(".stationfield-settings").exists()).toBe(false);
    wrapper.unmount();
    make(station("FOREIGN", { kind: "object", can_message: true, reported_by: "OH2RDG" }));
    expect(items()).toEqual(["show", "copy", "forget"]);
    expect(wrapper.find(".stationfield-settings").exists()).toBe(false);
  });

  it("says Open its card for a station with no position", () => {
    make(station("OH2PU-9", { lat: null, lon: null }));
    expect(wrapper.find("[data-item='show']").text()).toBe("Open its card");
  });

  it("has the queries off with RX only, and Message on", () => {
    make(station("OH2RDG"), { receiveOnly: true });
    expect(wrapper.find("[data-item='ask_status']").attributes("disabled")).toBeDefined();
    expect(wrapper.find("[data-item='message']").attributes("disabled")).toBeUndefined();
  });
});

describe("the settings in the field", () => {
  it("send the station's path and RF only as they are changed", async () => {
    make(station("OH2RDG"));
    expect(wrapper.find(".path-line").text()).toBe("Automatic: WIDE1-1,WIDE2-1");
    await wrapper.find("input[type='text']").setValue("OH2RCH-2");
    await wrapper.find("input[type='text']").trigger("change");
    expect(send).toHaveBeenCalledWith({ cmd: "set_station_path", call: "OH2RDG", path: "OH2RCH-2" });
    await wrapper.find(".rfonly input").setValue(true);
    expect(send).toHaveBeenCalledWith({ cmd: "set_station_rf_only", call: "OH2RDG", on: true });
  });

  it("send the whole alert as a tickbox is ticked or cleared, and the distance once it is changed to one the daemon takes", async () => {
    make(station("OH2RDG"));
    await tick("on_air").setValue(true);
    expect(send).toHaveBeenLastCalledWith({ cmd: "set_station_alert", call: "OH2RDG", on_air: true, within_km: null, direct: false });
    await tick("within").setValue(true);
    expect(send).toHaveBeenLastCalledWith({ cmd: "set_station_alert", call: "OH2RDG", on_air: true, within_km: 10, direct: false });
    const km = wrapper.find("input[type='number']");
    send.mockClear();
    await km.setValue(0);
    await km.trigger("change");
    expect(km.attributes("aria-invalid")).toBe("true");
    expect(send).not.toHaveBeenCalled();
    await km.setValue(25);
    await km.trigger("change");
    expect(send).toHaveBeenLastCalledWith({ cmd: "set_station_alert", call: "OH2RDG", on_air: true, within_km: 25, direct: false });
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
