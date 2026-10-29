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
  it("is in the station's panel with the station's alert ticked, and no longer in the menu of the row", async () => {
    make();
    await row("OH2XYZ").trigger("click");
    const panel = wrapper.find(".stationpanel");
    expect(panel.findAll("legend").map((l) => l.text())).toContain("Alert me when OH2XYZ…");
    expect(["on_air", "within", "direct"].map((name) => (panel.find(`input[data-alert='${name}']`).element as HTMLInputElement).checked)).toEqual([
      true,
      true,
      false,
    ]);
    await row("OH2XYZ").trigger("contextmenu", { clientX: 100, clientY: 120 });
    await nextTick();
    expect(wrapper.findAll("[role='menuitem']").map((i) => i.attributes("data-item"))).not.toContain("alert");
    expect(wrapper.find("[role='dialog']").exists()).toBe(false);
    expect(send).not.toHaveBeenCalledWith(expect.objectContaining({ cmd: "set_station_alert" }));
  });
});
