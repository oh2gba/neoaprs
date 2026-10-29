// The field under a row of the Stations table (StationRowDetail in StationsTable): a click opens it under the row as a click on a packet does in the Packets tab, one at a time, the same click closes it, Up and Down take it
// along, Esc in it closes it with the focus back on the row, and its buttons say to the page what the menu of the row says.
import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { nextTick, shallowRef, type ShallowRef } from "vue";
import StationsTable from "@/components/StationsTable.vue";
import { fakeDaemon, withDaemon } from "@/test/context";
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
const fields = () => wrapper.findAll("tbody tr.detail");
/** The call of the row the open field is under: the row just before it. */
const fieldUnder = (): string | undefined => (fields()[0]?.element.previousElementSibling as HTMLElement | null)?.dataset.call;
const button = (item: string) => wrapper.find(`.stationfield [data-item='${item}']`);
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

describe("the field under a row: opening and closing", () => {
  it("opens right under the row that is clicked, which is still selected as before, and spans every column", async () => {
    make();
    expect(fields()).toHaveLength(0);
    expect(row("OH2RDG").attributes("aria-expanded")).toBe("false");
    await row("OH2RDG").trigger("click");
    expect(selects()).toEqual([["OH2RDG", false]]);
    expect(fields()).toHaveLength(1);
    expect(fieldUnder()).toBe("OH2RDG");
    expect(row("OH2RDG").attributes("aria-expanded")).toBe("true");
    expect(fields()[0]?.find("td").attributes("colspan")).toBe(String(row("OH2RDG").findAll("td").length));
    expect(fields()[0]?.find("[role='group']").attributes("aria-label")).toBe("Actions and settings for OH2RDG");
  });

  it("is one at a time: a click on another row moves it there, and a click on its own row again closes it", async () => {
    make();
    await row("OH2RDG").trigger("click");
    await row("OH2XYZ").trigger("click");
    expect(fields()).toHaveLength(1);
    expect(fieldUnder()).toBe("OH2XYZ");
    expect(row("OH2RDG").attributes("aria-expanded")).toBe("false");
    await row("OH2XYZ").trigger("click");
    expect(fields()).toHaveLength(0);
    expect(selects().map(([call]) => call)).toEqual(["OH2RDG", "OH2XYZ", "OH2XYZ"]);
  });

  it("opens and closes with Enter on the row as with a click", async () => {
    make();
    await row("OH2XYZ").trigger("keydown", { key: "Enter" });
    expect(fieldUnder()).toBe("OH2XYZ");
    await row("OH2XYZ").trigger("keydown", { key: "Enter" });
    expect(fields()).toHaveLength(0);
  });

  it("is left as it is by a click with Ctrl, which adds a card", async () => {
    make();
    await row("OH2RDG").trigger("click", { ctrlKey: true });
    expect(selects()).toEqual([["OH2RDG", true]]);
    expect(fields()).toHaveLength(0);
    await row("OH2XYZ").trigger("click");
    await row("OH2RDG").trigger("click", { ctrlKey: true });
    expect(fieldUnder()).toBe("OH2XYZ");
  });

  it("goes along with Up and Down to the row they select, and is not opened by them when it is closed", async () => {
    make();
    await row("OH2RDG").trigger("keydown", { key: "ArrowDown" });
    expect(fields()).toHaveLength(0);
    await row("OH2RDG").trigger("click");
    await row("OH2RDG").trigger("keydown", { key: "ArrowDown" });
    expect(fieldUnder()).toBe("OH2XYZ");
    expect(document.activeElement).toBe(row("OH2XYZ").element);
    await row("OH2XYZ").trigger("keydown", { key: "Home" });
    expect(fieldUnder()).toBe("OH2GBA");
    expect(fields()).toHaveLength(1);
  });

  it("closes on Esc anywhere in it, with the focus back on its row, and the Esc does not go on to close the cards", async () => {
    make();
    await row("OH2XYZ").trigger("click");
    const path = fields()[0].find("input[type='text']");
    (path.element as HTMLInputElement).focus();
    const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    path.element.dispatchEvent(event);
    await nextTick();
    expect(event.defaultPrevented).toBe(true);
    expect(fields()).toHaveLength(0);
    expect(document.activeElement).toBe(row("OH2XYZ").element);
  });

  it("closes when its station leaves the list", async () => {
    make();
    await row("OH2XYZ").trigger("click");
    const next = new Map(stations.value);
    next.delete("OH2XYZ");
    stations.value = next;
    await nextTick();
    expect(fields()).toHaveLength(0);
    next.set("OH2XYZ", station("OH2XYZ", { distance_km: 40, last_heard: ago(30) }));
    stations.value = new Map(next);
    await nextTick();
    expect(fields()).toHaveLength(0);
  });

  it("adds only its own row: the rows of the stations stay as they were", async () => {
    make();
    const before = wrapper.findAll("tbody tr[data-call]").map((r) => r.html());
    await row("OH2RDG").trigger("click");
    expect(wrapper.findAll("tbody tr[data-call]").map((r) => r.html().replace('aria-expanded="true"', 'aria-expanded="false"'))).toEqual(before);
    expect(wrapper.findAll("tbody tr")).toHaveLength(4);
  });
});

describe("the buttons of the field say what the menu of the row says", () => {
  it("Message, the four queries, Show, Copy", async () => {
    make();
    await row("OH2RDG").trigger("click");
    await button("message").trigger("click");
    for (const kind of ["position", "status", "heard", "trace"]) await button(`ask_${kind}`).trigger("click");
    await button("show").trigger("click");
    await button("copy").trigger("click");
    expect(wrapper.emitted("message")).toEqual([["OH2RDG"]]);
    expect(wrapper.emitted("ask")).toEqual([
      ["OH2RDG", "position"],
      ["OH2RDG", "status"],
      ["OH2RDG", "heard"],
      ["OH2RDG", "trace"],
    ]);
    expect(selects().at(-1)).toEqual(["OH2RDG", false]);
    expect(wrapper.emitted("copy")).toEqual([["OH2RDG"]]);
    expect(fields()).toHaveLength(1);
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
    expect(forget().find(".twowords-off").text()).toBe("Really forget?");
    await forget().trigger("click");
    expect(wrapper.emitted("forget")).toBeUndefined();
    expect(forget().attributes("aria-label")).toBe("Really forget?");
    expect(forget().classes()).toContain("danger");
    expect(forget().find(".twowords-off").text()).toBe("Forget");
    expect(row("OH2RDG").find("button.forgetbtn").classes()).toContain("armed");
    await forget().trigger("click");
    expect(wrapper.emitted("forget")).toEqual([["OH2RDG"]]);
  });

  it("leaves the row's own buttons and its menu as they were", async () => {
    make();
    await row("OH2RDG").trigger("click");
    expect(row("OH2RDG").findAll("td.actions button")).toHaveLength(3);
    await row("OH2RDG").trigger("contextmenu", { clientX: 100, clientY: 120 });
    await nextTick();
    expect(wrapper.find("[role='menu']").exists()).toBe(true);
    expect(wrapper.findAll("[role='menuitem']").map((i) => i.attributes("data-item"))).toContain("alert");
  });
});
