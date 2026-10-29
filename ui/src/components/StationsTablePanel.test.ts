// The station panel of the Stations tab (StationPanel in StationsTable): fixed at the bottom of the tab, as the box of every tab, after the list and its foot; a click on a row (and Up, Down, Home and End) shows that station
// in it, the row stays marked and no row opens, grows or moves; its cross and Esc close it with the focus back on the row; its buttons say to the page what they do.
import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { nextTick, shallowRef, type ShallowRef } from "vue";
import StationsTable from "@/components/StationsTable.vue";
import { fakeDaemon, withDaemon } from "@/test/context";
import { cssRule } from "@/test/css";
import { ago, station, table } from "@/test/fixtures";
import type { StationRow } from "@/protocol/protocol";

let wrapper: VueWrapper;
let stations: ShallowRef<ReadonlyMap<string, StationRow>>;
const make = () => {
  stations = shallowRef<ReadonlyMap<string, StationRow>>(
    table(
      station("OH2GBA", { is_me: true, distance_km: null, bearing_deg: null, last_heard: ago(10) }),
      station("OH2RDG", { distance_km: 25, last_heard: ago(20) }),
      station("OH2XYZ", { distance_km: 40, last_heard: ago(30) }),
    ),
  );
  wrapper = mount(StationsTable, {
    props: { selected: null },
    attachTo: document.body,
    global: withDaemon(fakeDaemon({ stations, aging: { defaultMin: 0 } })),
  });
  return wrapper;
};
const row = (call: string) => wrapper.find(`tbody tr[data-call='${call}']`);
const panel = () => wrapper.find(".stationpanel");
const shown = (): string | undefined => (panel().exists() ? panel().find("legend .mono").text() : undefined);
const button = (item: string) => panel().find(`[data-item='${item}']`);
const selects = () => wrapper.emitted("select") ?? [];

beforeEach(() => {
  localStorage.clear();
  window.innerWidth = 1024;
  window.innerHeight = 768;
});
afterEach(() => {
  wrapper.unmount();
  document.body.replaceChildren();
});

describe("the station panel: where it is and what shows it", () => {
  it("is the box at the bottom of the tab, after the list and its foot, the look of the Bulletins and Email boxes, with the call as its legend", async () => {
    make();
    expect(panel().exists()).toBe(false);
    await row("OH2RDG").trigger("click");
    expect(selects()).toEqual([["OH2RDG", false]]);
    const pane = wrapper.find(".tablepane").element;
    expect(pane.lastElementChild).toBe(panel().element);
    expect(panel().element.previousElementSibling?.classList.contains("foot")).toBe(true);
    expect(panel().classes()).toEqual(expect.arrayContaining(["composebar", "boxed"]));
    expect(panel().find("fieldset.composebox").exists()).toBe(true);
    expect(shown()).toBe("OH2RDG");
    expect(panel().attributes("aria-label")).toBe("Actions and settings for OH2RDG");
  });

  it("shows the station of the row clicked next, and the same click again leaves it as it is; nothing in the list opens or moves", async () => {
    make();
    const before = wrapper.findAll("table.stations > tbody > tr").map((r) => r.html().replace(/ selected|aria-selected="true"/g, ""));
    await row("OH2RDG").trigger("click");
    await row("OH2XYZ").trigger("click");
    expect(shown()).toBe("OH2XYZ");
    await row("OH2XYZ").trigger("click");
    expect(shown()).toBe("OH2XYZ");
    expect(wrapper.findAll("table.stations > tbody > tr")).toHaveLength(3);
    expect(wrapper.findAll("table.stations > tbody > tr").map((r) => r.html().replace(/ selected|aria-selected="true"/g, ""))).toEqual(before);
    expect(wrapper.find("table.stations tr.detail").exists()).toBe(false);
  });

  it("shows the station of the row Enter is pressed on, and of the row Up, Down, Home and End select", async () => {
    make();
    await row("OH2XYZ").trigger("keydown", { key: "Enter" });
    expect(shown()).toBe("OH2XYZ");
    await row("OH2XYZ").trigger("keydown", { key: "ArrowUp" });
    expect(shown()).toBe("OH2RDG");
    expect(document.activeElement).toBe(row("OH2RDG").element);
    await row("OH2RDG").trigger("keydown", { key: "Home" });
    expect(shown()).toBe("OH2GBA");
    await row("OH2GBA").trigger("keydown", { key: "End" });
    expect(shown()).toBe("OH2XYZ");
  });

  it("is left as it is by a click with Ctrl, which adds a card", async () => {
    make();
    await row("OH2RDG").trigger("click", { ctrlKey: true });
    expect(selects()).toEqual([["OH2RDG", true]]);
    expect(panel().exists()).toBe(false);
    await row("OH2XYZ").trigger("click");
    await row("OH2RDG").trigger("click", { ctrlKey: true });
    expect(shown()).toBe("OH2XYZ");
  });

  it("closes by its cross, with the focus back on the row", async () => {
    make();
    await row("OH2XYZ").trigger("click");
    const cross = panel().find("legend button");
    expect(cross.attributes("aria-label")).toBe("Close the panel");
    await cross.trigger("click");
    expect(panel().exists()).toBe(false);
    expect(document.activeElement).toBe(row("OH2XYZ").element);
  });

  it("closes on Esc anywhere in it, with the focus back on the row, and the Esc does not go on to close the cards", async () => {
    make();
    await row("OH2XYZ").trigger("click");
    const path = panel().find(".stationpanel-settings input[type='text']");
    (path.element as HTMLInputElement).focus();
    const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    path.element.dispatchEvent(event);
    await nextTick();
    expect(event.defaultPrevented).toBe(true);
    expect(panel().exists()).toBe(false);
    expect(document.activeElement).toBe(row("OH2XYZ").element);
  });

  it("closes when its station leaves the list, and does not come back by itself", async () => {
    make();
    await row("OH2XYZ").trigger("click");
    const next = new Map(stations.value);
    next.delete("OH2XYZ");
    stations.value = next;
    await nextTick();
    expect(panel().exists()).toBe(false);
    next.set("OH2XYZ", station("OH2XYZ", { distance_km: 40, last_heard: ago(30) }));
    stations.value = new Map(next);
    await nextTick();
    expect(panel().exists()).toBe(false);
  });

  it("has a height of its own that scrolls inside: the rule gives it half the tab, whatever it holds, and its traffic a fixed height", () => {
    expect(cssRule(".composebar.stationpanel")).toMatch(/flex:\s*0 0 50%/);
    expect(cssRule(".size-phone .composebar.stationpanel")).toMatch(/flex-basis:\s*40%/); // (a phone keeps a few rows of the list)
    expect(cssRule(".stationpanel-body")).toMatch(/overflow-y:\s*auto/);
    expect(cssRule(".stationtraffic")).toMatch(/height:\s*14em/);
  });
});

describe("the buttons of the panel", () => {
  it("Message, the four queries, the own query, Show, Copy", async () => {
    make();
    await row("OH2RDG").trigger("click");
    await button("message").trigger("click");
    for (const kind of ["position", "status", "heard", "trace"]) await button(`ask_${kind}`).trigger("click");
    await panel().find("input[data-query='text']").setValue("?aprsh oh2gba-15");
    await panel().find("form.stationpanel-query").trigger("submit");
    await button("show").trigger("click");
    await button("copy").trigger("click");
    expect(wrapper.emitted("message")).toEqual([["OH2RDG"]]);
    expect(wrapper.emitted("ask")).toEqual([
      ["OH2RDG", "position", undefined],
      ["OH2RDG", "status", undefined],
      ["OH2RDG", "heard", undefined],
      ["OH2RDG", "trace", undefined],
      ["OH2RDG", "custom", "?APRSH OH2GBA-15"],
    ]);
    expect(selects().at(-1)).toEqual(["OH2RDG", false]);
    expect(wrapper.emitted("copy")).toEqual([["OH2RDG"]]);
    expect(shown()).toBe("OH2RDG");
  });

  it("Forget asks twice, armed together with the row's trash can, and keeps its width: both words are in it, the one not said hidden", async () => {
    make();
    await row("OH2RDG").trigger("click");
    const forget = () => button("forget");
    expect(forget().attributes("aria-label")).toBe("Forget");
    expect(
      forget()
        .findAll(".twowords > span")
        .map((s) => s.text()),
    ).toEqual(["Forget", "Really forget?"]);
    await forget().trigger("click");
    expect(wrapper.emitted("forget")).toBeUndefined();
    expect(forget().attributes("aria-label")).toBe("Really forget?");
    expect(forget().classes()).toContain("danger");
    expect(row("OH2RDG").find("button.forgetbtn").classes()).toContain("armed");
    await forget().trigger("click");
    expect(wrapper.emitted("forget")).toEqual([["OH2RDG"]]);
  });

  it("leaves the row's own buttons and its short menu as they were", async () => {
    make();
    await row("OH2RDG").trigger("click");
    expect(row("OH2RDG").findAll("td.actions button")).toHaveLength(2);
    await row("OH2RDG").trigger("contextmenu", { clientX: 100, clientY: 120 });
    await nextTick();
    expect(wrapper.findAll("[role='menuitem']").map((i) => i.attributes("data-item"))).toEqual(["copy", "show", "qrz"]);
  });
});
