import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StationsTable from "@/components/StationsTable.vue";
import { cssRule } from "@/test/css";
import { fakeDaemon, withDaemon } from "@/test/context";
import { ago, station, table } from "@/test/fixtures";

const rows = table(
  station("OH2GBA", { is_me: true, distance_km: null, bearing_deg: null, last_heard: ago(10) }),
  station("OH2RDG", { distance_km: 25, last_heard: ago(20) }),
  station("OH2PU-9", { distance_km: 16, last_heard: ago(30) }),
  station("EMAIL-2", { can_message: false, last_heard: ago(40) }),
  station("OH2OBJ", { kind: "object", can_message: false, reported_by: "OH2GBA", own: true, last_heard: ago(50) }),
  station("FOREIGN", { kind: "object", can_message: true, reported_by: "OH2RDG", last_heard: ago(60) }),
);
const make = () => mount(StationsTable, { props: { selected: null }, global: withDaemon(fakeDaemon({ stations: rows, aging: { defaultMin: 0 } })) });
const row = (wrapper: ReturnType<typeof make>, call: string) => wrapper.findAll("tbody tr").find((r) => r.find("td.call .callname").text() === call)!;
const message = (wrapper: ReturnType<typeof make>, call: string) => row(wrapper, call).find("td.actions button[aria-label^='Message']");
const forget = (wrapper: ReturnType<typeof make>, call: string) => row(wrapper, call).find("td.actions button.forgetbtn");

beforeEach(() => localStorage.clear());
afterEach(() => vi.useRealTimers());

describe("the buttons at the end of a row of the Stations table", () => {
  it("offer Message where the card does (a station that can be messaged, not ours, not an object) and Forget where the card does (not ours, not our own object)", () => {
    const wrapper = make();
    expect(message(wrapper, "OH2RDG").exists()).toBe(true);
    expect(message(wrapper, "OH2PU-9").exists()).toBe(true);
    for (const call of ["OH2GBA", "EMAIL-2", "OH2OBJ", "FOREIGN"]) expect(message(wrapper, call).exists(), call).toBe(false);
    for (const call of ["OH2RDG", "OH2PU-9", "EMAIL-2", "FOREIGN"]) expect(forget(wrapper, call).exists(), call).toBe(true);
    for (const call of ["OH2GBA", "OH2OBJ"]) expect(forget(wrapper, call).exists(), call).toBe(false);
  });

  it("are named for a screen reader and for the mouse by the call, and are plain buttons you can reach with the keyboard", () => {
    const wrapper = make();
    const msg = message(wrapper, "OH2RDG");
    const del = forget(wrapper, "OH2RDG");
    expect(msg.attributes("aria-label")).toBe("Message OH2RDG");
    expect(msg.attributes("title")).toBe("Message OH2RDG");
    expect(del.attributes("aria-label")).toBe("Forget OH2RDG");
    expect(del.attributes("title")).toBe("Forget OH2RDG");
    for (const button of [msg, del]) {
      expect(button.attributes("type")).toBe("button");
      expect(button.attributes("tabindex")).toBeUndefined();
      expect(button.find("svg").exists()).toBe(true);
    }
    expect(msg.find("path").attributes("d")).not.toBe(del.find("path").attributes("d"));
  });

  it("have a head cell without text, and keep the rows one line high", () => {
    const wrapper = make();
    expect(wrapper.findAll("thead th").at(-1)?.text()).toBe("");
    expect(cssRule(".grid.stations td")).toMatch(/height:\s*30px/);
    expect(cssRule(".grid.stations td.actions .xbtn")).toMatch(/min-height:\s*28px/);
  });

  it("send Message with the call, and do not select the row", async () => {
    const wrapper = make();
    await message(wrapper, "OH2RDG").trigger("click");
    expect(wrapper.emitted("message")).toEqual([["OH2RDG"]]);
    expect(wrapper.emitted("select")).toBeUndefined();
    await message(wrapper, "OH2RDG").trigger("keydown.enter");
    expect(wrapper.emitted("select")).toBeUndefined();
  });

  it("forget on the second press, like the card's Forget: the first says sure? and does nothing, and does not select the row", async () => {
    const wrapper = make();
    await forget(wrapper, "OH2RDG").trigger("click");
    expect(wrapper.emitted("forget")).toBeUndefined();
    expect(forget(wrapper, "OH2RDG").text()).toBe("sure?");
    expect(forget(wrapper, "OH2RDG").attributes("aria-label")).toBe("Really forget OH2RDG?");
    expect(forget(wrapper, "OH2PU-9").text()).toBe("");
    await forget(wrapper, "OH2RDG").trigger("click");
    expect(wrapper.emitted("forget")).toEqual([["OH2RDG"]]);
    expect(forget(wrapper, "OH2RDG").text()).toBe("");
    expect(wrapper.emitted("select")).toBeUndefined();
    await forget(wrapper, "OH2RDG").trigger("keydown.enter");
    expect(wrapper.emitted("select")).toBeUndefined();
  });

  it("forget the first press after 5 s, and arming another station disarms the first", async () => {
    vi.useFakeTimers();
    const wrapper = make();
    await forget(wrapper, "OH2RDG").trigger("click");
    vi.advanceTimersByTime(5001);
    await wrapper.vm.$nextTick();
    expect(forget(wrapper, "OH2RDG").text()).toBe("");
    await forget(wrapper, "OH2RDG").trigger("click");
    await forget(wrapper, "OH2PU-9").trigger("click");
    expect(forget(wrapper, "OH2RDG").text()).toBe("");
    expect(forget(wrapper, "OH2PU-9").text()).toBe("sure?");
    expect(wrapper.emitted("forget")).toBeUndefined();
  });

  it("do not stop a click on the rest of the row from selecting it", async () => {
    const wrapper = make();
    await row(wrapper, "OH2RDG").trigger("click");
    expect(wrapper.emitted("select")).toEqual([["OH2RDG", false]]);
  });
});
