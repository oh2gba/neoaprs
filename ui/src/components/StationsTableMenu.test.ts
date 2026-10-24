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
const row = (call: string) => wrapper.findAll("tbody tr").find((r) => r.find("td.call").text() === call)!;
const menu = () => wrapper.find("[role='menu']");
const items = () => wrapper.findAll("[role='menuitem']");
const labels = () => items().map((i) => i.text());
const item = (name: string) => items().find((i) => i.attributes("data-item") === name)!;
const more = (call: string) => row(call).find("button.morebtn");
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

  it("opens from the ... button at the end of the row, under it, and the button again closes it", async () => {
    make();
    expect(more("OH2RDG").attributes("aria-label")).toBe("More actions for OH2RDG");
    expect(more("OH2RDG").attributes("aria-haspopup")).toBe("menu");
    expect(more("OH2RDG").attributes("aria-expanded")).toBe("false");
    await more("OH2RDG").trigger("click");
    await wrapper.vm.$nextTick();
    expect(menu().exists()).toBe(true);
    expect(more("OH2RDG").attributes("aria-expanded")).toBe("true");
    expect(wrapper.emitted("select")).toBeUndefined(); // (the click is not the row's)
    await more("OH2RDG").trigger("pointerdown");
    document.dispatchEvent(new Event("pointerdown")); // (a press outside the menu closes it before the click of the button comes)
    await more("OH2RDG").trigger("click");
    expect(menu().exists()).toBe(false);
  });

  it("has the ... button on every row, the last of the buttons", () => {
    make();
    for (const call of ["OH2GBA", "OH2RDG", "EMAIL-2", "OH2OBJ", "FOREIGN"]) {
      const buttons = row(call).findAll("td.actions button");
      expect(buttons.at(-1)?.classes(), call).toContain("morebtn");
    }
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
  it("has Message, the four queries, Show on map, Copy, QRZ and Forget for a station that takes messages", async () => {
    make();
    await rightClick("OH2RDG");
    expect(labels()).toEqual([
      "Message",
      "Ask for position",
      "Ask for status",
      "Ask what it hears direct",
      "Trace the route",
      "Show on map",
      "Copy call",
      "QRZ page",
      "Forget",
    ]);
    expect(menu().findAll("[role='separator']")).toHaveLength(2);
    expect(menu().text()).toContain("Many stations don't answer queries.");
  });

  it("opens its card instead of showing it on the map for a station with no position", async () => {
    make();
    await rightClick("OH2PU-9");
    expect(labels()).toContain("Open its card");
    expect(labels()).not.toContain("Show on map");
  });

  it("has no Message and no query where the card has no Message, and no note about them", async () => {
    make();
    await rightClick("EMAIL-2");
    expect(labels()).toEqual(["Show on map", "Copy call", "QRZ page", "Forget"]);
    expect(menu().text()).not.toContain("answer queries");
    expect(menu().findAll("[role='separator']")).toHaveLength(1);
  });

  it("has Show, Copy and the QRZ page for our own station, and no Forget", async () => {
    make();
    await rightClick("OH2GBA");
    expect(labels()).toEqual(["Show on map", "Copy call", "QRZ page"]);
  });

  it("has Show and Copy for an object of ours, and for an object of another station Forget besides, with no QRZ page", async () => {
    make();
    await rightClick("OH2OBJ");
    expect(labels()).toEqual(["Show on map", "Copy call"]);
    await rightClick("FOREIGN");
    expect(labels()).toEqual(["Show on map", "Copy call", "Forget"]);
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
    expect(at()).toBe(8);
    await menu().trigger("keydown", { key: "ArrowDown" });
    expect(at()).toBe(0);
    await menu().trigger("keydown", { key: "End" });
    expect(at()).toBe(8);
    await menu().trigger("keydown", { key: "Home" });
    expect(at()).toBe(0);
  });

  it("closes on Esc with the focus back on the ... button it came from, on Tab, and on a press outside it", async () => {
    make();
    await more("OH2RDG").trigger("click");
    await wrapper.vm.$nextTick();
    await menu().trigger("keydown", { key: "Escape" });
    expect(menu().exists()).toBe(false);
    expect(document.activeElement).toBe(more("OH2RDG").element);

    await more("OH2RDG").trigger("click");
    await menu().trigger("keydown", { key: "Tab" });
    expect(menu().exists()).toBe(false);

    await more("OH2RDG").trigger("click");
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
  it("Message writes to the station and closes the menu", async () => {
    make();
    await rightClick("OH2RDG");
    await item("message").trigger("click");
    expect(wrapper.emitted("message")).toEqual([["OH2RDG"]]);
    expect(menu().exists()).toBe(false);
  });

  it.each([
    ["ask_position", "position"],
    ["ask_status", "status"],
    ["ask_heard", "heard"],
    ["ask_trace", "trace"],
  ])("%s asks the station the %s query once and closes the menu", async (name, kind) => {
    make();
    await rightClick("OH2RDG");
    await item(name).trigger("click");
    expect(wrapper.emitted("ask")).toEqual([["OH2RDG", kind]]);
    expect(wrapper.emitted("message")).toBeUndefined();
    expect(menu().exists()).toBe(false);
  });

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

  it("Forget asks twice, like the trash can of the row: the first press says Really forget? and keeps the menu, the second forgets and closes it", async () => {
    make();
    await rightClick("OH2RDG");
    await item("forget").trigger("click");
    expect(wrapper.emitted("forget")).toBeUndefined();
    expect(menu().exists()).toBe(true);
    expect(item("forget").text()).toBe("Really forget?");
    expect(row("OH2RDG").find("button.forgetbtn").classes()).toContain("armed"); // (one armed button, the same as the row's)
    await item("forget").trigger("click");
    expect(wrapper.emitted("forget")).toEqual([["OH2RDG"]]);
    expect(menu().exists()).toBe(false);
  });

  it("Forget goes back to asking after 5 seconds", async () => {
    vi.useFakeTimers();
    make();
    await rightClick("OH2RDG");
    await item("forget").trigger("click");
    expect(item("forget").text()).toBe("Really forget?");
    vi.advanceTimersByTime(5001);
    await wrapper.vm.$nextTick();
    expect(item("forget").text()).toBe("Forget");
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
