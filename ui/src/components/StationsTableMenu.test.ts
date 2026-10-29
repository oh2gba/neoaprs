import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StationsTable from "@/components/StationsTable.vue";
import { fakeDaemon, withDaemon } from "@/test/context";
import { ago, station, table } from "@/test/fixtures";

const rows = table(
  station("OH2GBA", { is_me: true, distance_km: null, bearing_deg: null, last_heard: ago(10) }),
  station("OH2RDG", { distance_km: 25, last_heard: ago(20) }),
  station("OH2PU-9", { distance_km: 16, last_heard: ago(30), lat: null, lon: null }),
  station("EMAIL-2", { can_message: false, last_heard: ago(40) }),
  station("OH2OBJ", { kind: "object", can_message: false, reported_by: "OH2GBA", own: true, last_heard: ago(50) }),
  station("FOREIGN", { kind: "object", can_message: true, reported_by: "OH2RDG", last_heard: ago(60) }),
);
let wrapper: VueWrapper;
const make = () => {
  wrapper = mount(StationsTable, {
    props: { selected: null },
    attachTo: document.body,
    global: withDaemon(fakeDaemon({ stations: rows, aging: { defaultMin: 0 } })),
  });
  return wrapper;
};
const row = (call: string) => wrapper.findAll("tbody tr").find((r) => r.find("td.call .callname").text() === call)!;
const menu = () => wrapper.find("[role='menu']");
const items = () => wrapper.findAll("[role='menuitem']");
const labels = () => items().map((i) => i.text());
const item = (name: string) => items().find((i) => i.attributes("data-item") === name)!;
const rightClick = async (call: string, x = 100, y = 120) => {
  await row(call).trigger("contextmenu", { clientX: x, clientY: y });
};
const touch = (extra: Record<string, unknown> = {}) => ({ pointerType: "touch", isPrimary: true, clientX: 60, clientY: 80, ...extra });

beforeEach(() => {
  localStorage.clear();
  window.innerWidth = 1024;
  window.innerHeight = 768;
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  wrapper.unmount();
  document.body.replaceChildren();
});

describe("the menu of a row of the Stations table: opening", () => {
  it("opens on a right-click at the pointer, without the browser's own menu, and closes on Esc with the focus back on the row", async () => {
    make();
    const event = new MouseEvent("contextmenu", { clientX: 100, clientY: 120, bubbles: true, cancelable: true });
    row("OH2RDG").element.dispatchEvent(event);
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    expect(event.defaultPrevented).toBe(true);
    expect(menu().exists()).toBe(true);
    expect(menu().attributes("aria-label")).toBe("Actions for OH2RDG");
    expect(menu().attributes("style")).toContain("left: 100px");
    expect(menu().attributes("style")).toContain("top: 120px");
    await menu().trigger("keydown", { key: "Escape" });
    expect(menu().exists()).toBe(false);
    expect(document.activeElement).toBe(row("OH2RDG").element);
  });

  it("opens on a long press with a finger, not on a short one, not with the mouse, and not when the finger moves away", async () => {
    vi.useFakeTimers();
    make();
    await row("OH2RDG").trigger("pointerdown", touch());
    vi.advanceTimersByTime(300);
    await row("OH2RDG").trigger("pointerup", touch());
    vi.advanceTimersByTime(1000);
    expect(menu().exists()).toBe(false);

    await row("OH2RDG").trigger("pointerdown", { ...touch(), pointerType: "mouse" });
    vi.advanceTimersByTime(1000);
    expect(menu().exists()).toBe(false);

    await row("OH2RDG").trigger("pointerdown", touch());
    vi.advanceTimersByTime(200);
    await row("OH2RDG").trigger("pointermove", touch({ clientY: 140 }));
    vi.advanceTimersByTime(1000);
    expect(menu().exists()).toBe(false);

    await row("OH2RDG").trigger("pointerdown", touch());
    vi.advanceTimersByTime(499);
    expect(menu().exists()).toBe(false);
    vi.advanceTimersByTime(2);
    await wrapper.vm.$nextTick();
    expect(menu().exists()).toBe(true);
    expect(menu().attributes("style")).toContain("left: 60px");
    expect(menu().attributes("aria-label")).toBe("Actions for OH2RDG");
  });

  it("does not select the row with the click of the finger that is lifted after a long press, but does with the next tap", async () => {
    vi.useFakeTimers();
    make();
    await row("OH2RDG").trigger("pointerdown", touch());
    vi.advanceTimersByTime(600);
    await row("OH2RDG").trigger("pointerup", touch());
    await row("OH2RDG").trigger("click");
    expect(wrapper.emitted("select")).toBeUndefined();
    await row("OH2RDG").trigger("click");
    expect(wrapper.emitted("select")).toEqual([["OH2RDG", false]]);
  });

  it("has no ... button: a click on the row opens the station's panel, and the row keeps its Message and Forget", () => {
    make();
    expect(row("OH2RDG").find("td.actions button[aria-haspopup]").exists()).toBe(false);
    expect(
      row("OH2RDG")
        .findAll("td.actions button")
        .map((b) => b.attributes("aria-label")),
    ).toEqual(["Message OH2RDG", "Forget OH2RDG"]);
  });

  it("moves the focus to the first item, and keeps a second menu from being open with the first", async () => {
    make();
    await rightClick("OH2RDG");
    await wrapper.vm.$nextTick();
    expect(document.activeElement).toBe(items()[0]?.element);
    await rightClick("EMAIL-2", 300, 200);
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll("[role='menu']")).toHaveLength(1);
    expect(menu().attributes("aria-label")).toBe("Actions for EMAIL-2");
  });

  it("is kept inside the window", async () => {
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
      width: 220,
      height: 300,
      left: 0,
      top: 0,
      right: 220,
      bottom: 300,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });
    make();
    await rightClick("OH2RDG", 1000, 700);
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    expect(menu().attributes("style")).toContain("left: 796px"); // 1024 - 220 - 8
    expect(menu().attributes("style")).toContain("top: 460px"); // 768 - 300 - 8
    await rightClick("OH2RDG", 2, 3);
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    expect(menu().attributes("style")).toContain("left: 8px");
    expect(menu().attributes("style")).toContain("top: 8px");
  });
});

describe("the menu of a row of the Stations table: what it offers", () => {
  it("has only Copy call, Show on map and the QRZ page, as short as the Packets tab's: the rest is in the station's panel", async () => {
    make();
    await rightClick("OH2RDG");
    expect(labels()).toEqual(["Copy call", "Show on map", "QRZ page"]);
    expect(menu().findAll("[role='separator']")).toHaveLength(0);
    expect(menu().text()).not.toContain("answer");
  });

  it("opens its card instead of showing it on the map for a station with no position", async () => {
    make();
    await rightClick("OH2PU-9");
    expect(labels()).toEqual(["Copy call", "Open its card", "QRZ page"]);
  });

  it("is the same for our own station and one that takes no message, and has no QRZ page for an object", async () => {
    make();
    await rightClick("OH2GBA");
    expect(labels()).toEqual(["Copy call", "Show on map", "QRZ page"]);
    await rightClick("EMAIL-2");
    expect(labels()).toEqual(["Copy call", "Show on map", "QRZ page"]);
    await rightClick("OH2OBJ");
    expect(labels()).toEqual(["Copy call", "Show on map"]);
    await rightClick("FOREIGN");
    expect(labels()).toEqual(["Copy call", "Show on map"]);
  });

  it("links the QRZ page of the base call, in a tab of its own", async () => {
    make();
    await rightClick("OH2PU-9");
    const link = item("qrz");
    expect(link.element.tagName).toBe("A");
    expect(link.attributes("href")).toBe("https://www.qrz.com/db/OH2PU");
    expect(link.attributes("target")).toBe("_blank");
    expect(link.attributes("rel")).toContain("noopener");
    link.element.addEventListener("click", (event) => event.preventDefault()); // (the test does not go to QRZ)
    await link.trigger("click");
    expect(menu().exists()).toBe(false);
  });
});

describe("the menu of a row of the Stations table: the keyboard", () => {
  it("moves with Down and Up (round the ends), Home and End", async () => {
    make();
    await rightClick("OH2RDG");
    await wrapper.vm.$nextTick();
    const at = () => items().findIndex((i) => i.element === document.activeElement);
    expect(at()).toBe(0);
    await menu().trigger("keydown", { key: "ArrowDown" });
    expect(at()).toBe(1);
    await menu().trigger("keydown", { key: "ArrowUp" });
    await menu().trigger("keydown", { key: "ArrowUp" });
    expect(at()).toBe(2);
    await menu().trigger("keydown", { key: "ArrowDown" });
    expect(at()).toBe(0);
    await menu().trigger("keydown", { key: "End" });
    expect(at()).toBe(2);
    await menu().trigger("keydown", { key: "Home" });
    expect(at()).toBe(0);
  });

  it("closes on Tab, and on a press outside it", async () => {
    make();
    await rightClick("OH2RDG");
    await menu().trigger("keydown", { key: "Tab" });
    expect(menu().exists()).toBe(false);

    await rightClick("OH2RDG");
    await wrapper.vm.$nextTick();
    document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(menu().exists()).toBe(false);
  });

  it("does not let the Esc go on to the page (it would close the newest card)", async () => {
    make();
    const seen = vi.fn();
    document.addEventListener("keydown", seen);
    await rightClick("OH2RDG");
    await wrapper.vm.$nextTick();
    items()[0]?.element.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    document.removeEventListener("keydown", seen);
    expect(seen).not.toHaveBeenCalled();
  });

  it("opens with the menu key on a row, at the row", async () => {
    make();
    await row("OH2RDG").trigger("contextmenu", { clientX: 0, clientY: 0 });
    expect(menu().exists()).toBe(true);
  });
});

describe("the menu of a row of the Stations table: what its items do", () => {
  it("Show selects the station like a click on its row, without Ctrl", async () => {
    make();
    await rightClick("OH2RDG");
    await item("show").trigger("click");
    expect(wrapper.emitted("select")).toEqual([["OH2RDG", false]]);
    expect(menu().exists()).toBe(false);
  });

  it("Copy call copies the call", async () => {
    make();
    await rightClick("OH2PU-9");
    await item("copy").trigger("click");
    expect(wrapper.emitted("copy")).toEqual([["OH2PU-9"]]);
    expect(menu().exists()).toBe(false);
  });

  it("goes when the station is forgotten under it", async () => {
    const daemon = fakeDaemon({ stations: rows, aging: { defaultMin: 0 } });
    wrapper = mount(StationsTable, { props: { selected: null }, attachTo: document.body, global: withDaemon(daemon) });
    await rightClick("OH2RDG");
    expect(menu().exists()).toBe(true);
    const gone = new Map(rows);
    gone.delete("OH2RDG");
    daemon.stations.value = gone;
    await wrapper.vm.$nextTick();
    expect(menu().exists()).toBe(false);
  });
});
