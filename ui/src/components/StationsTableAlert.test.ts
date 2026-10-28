import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, shallowReactive } from "vue";
import StationsTable from "@/components/StationsTable.vue";
import { useStationPrefs } from "@/composables/useStationPrefs";
import { fakeDaemon, withDaemon } from "@/test/context";
import { ago, station, table } from "@/test/fixtures";
import type { Command, StationPref } from "@/protocol/protocol";

const rows = table(
  station("OH2GBA", { is_me: true, distance_km: null, bearing_deg: null, last_heard: ago(10) }),
  station("OH2RDG", { distance_km: 25, last_heard: ago(20) }),
  station("OH2XYZ", { distance_km: 40, last_heard: ago(30) }),
);
let wrapper: VueWrapper;
let book: Map<string, StationPref>;
let send: ReturnType<typeof vi.fn<(command: Command) => boolean>>;
const make = (home: { lat: number; lon: number } | null = { lat: 60.17, lon: 24.94 }) => {
  send = vi.fn((_command: Command) => true);
  book = shallowReactive(new Map<string, StationPref>([["OH2XYZ", { path: null, rf_only: false, alert: { on_air: true, within_km: 10, direct: false } }]]));
  const daemon = fakeDaemon({ stations: rows, send, home, prefs: useStationPrefs(book, send) });
  wrapper = mount(StationsTable, { props: { selected: null }, attachTo: document.body, global: withDaemon(daemon) });
  return wrapper;
};
const row = (call: string) => wrapper.findAll("tbody tr").find((r) => r.find("td.call .callname").text() === call)!;
const box = () => wrapper.find("[role='dialog']");
const tick = (name: string) => box().find(`input[data-alert='${name}']`);
const km = () => box().find("input[type='number']");
const button = (text: string) =>
  box()
    .findAll("button")
    .find((b) => b.text() === text)!;
async function openFor(call: string): Promise<void> {
  await row(call).trigger("contextmenu", { clientX: 100, clientY: 120 });
  await nextTick();
  await wrapper
    .findAll("[role='menuitem']")
    .find((i) => i.attributes("data-item") === "alert")!
    .trigger("click");
  await nextTick();
  await nextTick();
}

beforeEach(() => {
  localStorage.clear();
  window.innerWidth = 1024;
  window.innerHeight = 768;
});
afterEach(() => {
  wrapper.unmount();
  document.body.replaceChildren();
});

describe("the bell of a station with an alert set", () => {
  it("is in the row of that station only, with what it watches as its title, and every row has its place so that nothing moves", () => {
    make();
    const bell = row("OH2XYZ").find("td.call .alert-bell");
    expect(bell.find("svg").attributes("aria-label")).toBe("Alert when on the air, within 10 km");
    expect(bell.attributes("title")).toBe("Alert when on the air, within 10 km");
    for (const call of ["OH2GBA", "OH2RDG"]) {
      expect(row(call).find("td.call .alert-bell").exists(), call).toBe(true);
      expect(row(call).find("td.call .alert-bell svg").exists(), call).toBe(false);
    }
  });

  it("comes and goes with the station's entry of the daemon", async () => {
    make();
    book.set("OH2RDG", { path: null, rf_only: false, alert: { on_air: false, within_km: null, direct: true } });
    book.delete("OH2XYZ");
    await nextTick();
    expect(row("OH2RDG").find(".alert-bell svg").attributes("aria-label")).toBe("Alert when heard direct");
    expect(row("OH2XYZ").find(".alert-bell svg").exists()).toBe(false);
  });
});

describe("Alert me when…", () => {
  it("opens a box where the menu was, with the station's alert ticked and the focus on its first tickbox, and Esc closes it with the focus back on the row", async () => {
    make();
    await openFor("OH2XYZ");
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
    expect(box().attributes("aria-label")).toBe("Alert me when OH2XYZ…");
    expect(box().attributes("style")).toContain("left: 100px");
    expect([tick("on_air"), tick("within"), tick("direct")].map((t) => (t.element as HTMLInputElement).checked)).toEqual([true, true, false]);
    expect((km().element as HTMLInputElement).value).toBe("10");
    expect(document.activeElement).toBe(tick("on_air").element);
    await box().trigger("keydown", { key: "Escape" });
    expect(box().exists()).toBe(false);
    expect(document.activeElement).toBe(row("OH2XYZ").element);
    expect(send).not.toHaveBeenCalled();
  });

  it("starts with nothing ticked and 10 km for a station without one, and Save sends the whole alert and gives the focus back", async () => {
    make();
    await openFor("OH2RDG");
    expect([tick("on_air"), tick("within"), tick("direct")].map((t) => (t.element as HTMLInputElement).checked)).toEqual([false, false, false]);
    expect(km().attributes("disabled")).toBeDefined();
    await tick("within").setValue(true);
    await km().setValue(8);
    await tick("direct").setValue(true);
    await box().find("form").trigger("submit");
    expect(send).toHaveBeenCalledWith({ cmd: "set_station_alert", call: "OH2RDG", on_air: false, within_km: 8, direct: true });
    expect(box().exists()).toBe(false);
    expect(document.activeElement).toBe(row("OH2RDG").element);
  });

  it("takes the alert away when everything is unticked, and Cancel sends nothing", async () => {
    make();
    await openFor("OH2XYZ");
    await button("Cancel").trigger("click");
    expect(send).not.toHaveBeenCalled();
    await openFor("OH2XYZ");
    await tick("on_air").setValue(false);
    await tick("within").setValue(false);
    await button("Save").trigger("click");
    expect(send).toHaveBeenCalledWith({ cmd: "set_station_alert", call: "OH2XYZ", on_air: false, within_km: null, direct: false });
  });

  it("will not save a distance the daemon would refuse, and says when our position is missing", async () => {
    make(null);
    await openFor("OH2XYZ");
    expect(box().text()).toContain("Needs your position (Settings)");
    for (const bad of [0, 1001, 2.5]) {
      await km().setValue(bad);
      expect(button("Save").attributes("disabled"), String(bad)).toBeDefined();
      expect(km().attributes("aria-invalid")).toBe("true");
    }
    await km().setValue(1000);
    expect(button("Save").attributes("disabled")).toBeUndefined();
  });

  it("is not offered for our own station", async () => {
    make();
    await row("OH2GBA").trigger("contextmenu", { clientX: 100, clientY: 120 });
    await nextTick();
    expect(wrapper.findAll("[role='menuitem']").map((i) => i.attributes("data-item"))).not.toContain("alert");
  });
});
