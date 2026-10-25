import "@/test/mockmap";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import App from "@/App.vue";
import { FakeMap, FakeMarker, resetFakes } from "@/test/fakemap";
import { FakeSocket } from "@/test/fakesocket";
import { NOW, ago, configValues, hello, station, status, tncState } from "@/test/fixtures";

const CALLS = ["OH2ZWA", "OH2ZWB", "OH2ZWC", "OH2ZWD", "OH2ZWE", "OH2ZWF"];
const stations = {
  OH2GBA: station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94, symbol_table: "", symbol_code: "", distance_km: null, bearing_deg: null }),
  ...Object.fromEntries(
    CALLS.map((call, i) => [
      call,
      station(call, { symbol_code: "_", symbol_name: "Weather station", lat: 60.1 + i / 10, lon: 24.6 + i / 10, last_heard: ago(10 + i) }),
    ]),
  ),
};

function resize(width: number, height: number): void {
  window.innerWidth = width;
  window.innerHeight = height;
  window.dispatchEvent(new Event("resize"));
}

const opened: VueWrapper[] = [];
async function open(width: number, height: number, call = "OH2GBA") {
  resize(width, height);
  const wrapper = mount(App, { attachTo: document.body });
  opened.push(wrapper);
  await flushPromises();
  const socket = FakeSocket.last();
  socket.say(hello());
  socket.say({ type: "state", topic: "stations", rev: 0, value: stations });
  socket.say({ type: "state", topic: "tnc", rev: 0, value: tncState() });
  socket.say({ type: "state", topic: "config", rev: 0, value: configValues({ "station/call": call }) });
  socket.say(status());
  await flushPromises();
  return { wrapper, socket };
}

const row = (wrapper: VueWrapper, call: string) => wrapper.findAll("#pane-stations tbody tr").find((r) => r.find("td.call").text() === call);
const cards = (wrapper: VueWrapper) => wrapper.findAll(".cardstack .card").map((card) => card.find("strong").text());
const marker = (call: string) => FakeMarker.live().find((m) => m.element.textContent === call);
const marked = () =>
  FakeMarker.live()
    .filter((m) => m.element.classList.contains("stn--selected"))
    .map((m) => m.element.textContent);
const ctrl = (call: string) => marker(call)?.element.dispatchEvent(new MouseEvent("click", { bubbles: true, ctrlKey: true }));
const esc = () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
const root = (wrapper: VueWrapper) => wrapper.find(".app").classes();
const route = () => FakeMap.last().getSource("route")?.setData.mock.calls.at(-1)?.[0] as { features: { properties: Record<string, unknown> }[] } | undefined;

beforeEach(() => {
  FakeSocket.all = [];
  resetFakes();
  localStorage.clear();
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.useFakeTimers({ toFake: ["Date"] }); // (the clock stands at the fixtures' time, so that nothing has timed out)
  vi.setSystemTime(NOW);
});
afterEach(() => {
  for (const wrapper of opened.splice(0)) wrapper.unmount();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.body.replaceChildren();
  resize(1024, 768);
});

describe("several station cards on a desktop (1400 by 900)", () => {
  it("opens one card for a plain click, on a marker or a row, and the next plain click replaces it", async () => {
    const { wrapper } = await open(1400, 900);
    marker("OH2ZWA")?.element.click();
    await nextTick();
    expect(cards(wrapper)).toEqual(["OH2ZWA"]);
    await row(wrapper, "OH2ZWB")?.trigger("click");
    expect(cards(wrapper)).toEqual(["OH2ZWB"]);
    marker("OH2ZWC")?.element.click();
    await nextTick();
    expect(cards(wrapper)).toEqual(["OH2ZWC"]);
  });

  it("adds a card with Ctrl+click on a row or a marker, and closes it with the same click again", async () => {
    const { wrapper } = await open(1400, 900);
    await row(wrapper, "OH2ZWA")?.trigger("click", { ctrlKey: true });
    await row(wrapper, "OH2ZWB")?.trigger("click", { metaKey: true });
    ctrl("OH2ZWC");
    await nextTick();
    expect(cards(wrapper)).toEqual(["OH2ZWA", "OH2ZWB", "OH2ZWC"]);
    expect(marked().sort()).toEqual(["OH2ZWA", "OH2ZWB", "OH2ZWC"]);
    expect(wrapper.findAll("#pane-stations tr.selected")).toHaveLength(3);
    await row(wrapper, "OH2ZWB")?.trigger("click", { ctrlKey: true });
    ctrl("OH2ZWA");
    await nextTick();
    expect(cards(wrapper)).toEqual(["OH2ZWC"]);
  });

  it("draws the route of the newest card only: the same as for that station alone", async () => {
    const { wrapper } = await open(1400, 900);
    FakeMap.last().fire("style.load");
    await row(wrapper, "OH2ZWB")?.trigger("click");
    const alone = JSON.stringify(route());
    expect(route()?.features.length).toBeGreaterThan(0);
    await row(wrapper, "OH2ZWA")?.trigger("click", { ctrlKey: true });
    await row(wrapper, "OH2ZWB")?.trigger("click", { ctrlKey: true }); // (closes B: the route is A's now)
    expect(JSON.stringify(route())).not.toBe(alone);
    await row(wrapper, "OH2ZWB")?.trigger("click", { ctrlKey: true });
    expect(cards(wrapper)).toEqual(["OH2ZWA", "OH2ZWB"]);
    expect(JSON.stringify(route())).toBe(alone);
  });

  it("does not fly the map for a card that is added, and flies for a plain click", async () => {
    const { wrapper } = await open(1400, 900);
    await row(wrapper, "OH2ZWA")?.trigger("click");
    const flights = FakeMap.last().flights.length;
    expect(flights).toBeGreaterThan(0);
    await row(wrapper, "OH2ZWB")?.trigger("click", { ctrlKey: true });
    expect(FakeMap.last().flights).toHaveLength(flights);
  });

  it("closes the oldest card when there are more than four, the most a desktop has", async () => {
    const { wrapper } = await open(1400, 900);
    for (const call of CALLS) await row(wrapper, call)?.trigger("click", { ctrlKey: true });
    expect(cards(wrapper)).toEqual(["OH2ZWC", "OH2ZWD", "OH2ZWE", "OH2ZWF"]);
  });

  it("closes the oldest card when the row of cards is wider than the map has room for, and never makes a card narrower", async () => {
    Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 1000 }); // (the row: 980 px between the margins)
    Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, get: () => 300 });
    try {
      const { wrapper } = await open(1920, 1080);
      for (const call of CALLS.slice(0, 3)) await row(wrapper, call)?.trigger("click", { ctrlKey: true });
      await flushPromises();
      expect(cards(wrapper)).toEqual(["OH2ZWA", "OH2ZWB", "OH2ZWC"]); // 3 x 300 + 2 x 8 = 916
      await row(wrapper, "OH2ZWD")?.trigger("click", { ctrlKey: true });
      await flushPromises();
      expect(cards(wrapper)).toEqual(["OH2ZWB", "OH2ZWC", "OH2ZWD"]); // 4 x 300 + 24 = 1224
    } finally {
      for (const name of ["clientWidth", "offsetWidth"]) Reflect.deleteProperty(HTMLElement.prototype, name);
    }
  });

  it("has Message these N beside Close all, which opens the group compose of the Messages tab for the stations of the cards", async () => {
    const { wrapper } = await open(1400, 900);
    await row(wrapper, "OH2ZWA")?.trigger("click");
    expect(wrapper.find(".cards-message").exists()).toBe(false);
    await row(wrapper, "OH2ZWB")?.trigger("click", { ctrlKey: true });
    await row(wrapper, "OH2ZWC")?.trigger("click", { ctrlKey: true });
    expect(wrapper.find(".cards-message").text()).toBe("Message these 3");
    await wrapper.find(".cards-message").trigger("click");
    await flushPromises();
    expect(wrapper.find("[aria-selected='true']").text()).toContain("Messages");
    expect(wrapper.find("#pane-messages").text()).toContain("OH2ZWA");
    expect(wrapper.find("#pane-messages").text()).toContain("OH2ZWC");
  });

  it("opens the conversation with a call that is not in the Stations table, from the Message button under the empty result", async () => {
    const { wrapper } = await open(1400, 900);
    await wrapper.find("#tab-stations").trigger("click");
    await wrapper.find("#pane-stations input[type='search']").setValue("oh9new");
    await wrapper.find("#pane-stations tr.stranger button").trigger("click");
    await flushPromises();
    expect(wrapper.find("[aria-selected='true']").text()).toContain("Messages");
    expect(wrapper.find("#pane-messages").text()).toContain("OH9NEW");
    await wrapper.find("#tab-stations").trigger("click");
    await wrapper.find("#pane-stations input[type='search']").setValue("OH2GBA"); // (our own call: no button)
    expect(wrapper.find("#pane-stations tr.stranger").exists()).toBe(false);
  });

  it("opens the conversation from the speech bubble of a row, without opening the row's card, and forgets from its trash can on the second press, closing the card of that station", async () => {
    const { wrapper, socket } = await open(1400, 900);
    await wrapper.find("#tab-stations").trigger("click");
    await row(wrapper, "OH2ZWB")?.find("button[aria-label='Message OH2ZWB']").trigger("click");
    await flushPromises();
    expect(cards(wrapper)).toEqual([]);
    expect(wrapper.find("[aria-selected='true']").text()).toContain("Messages");
    expect(wrapper.find("#pane-messages").text()).toContain("OH2ZWB");
    await wrapper.find("#tab-stations").trigger("click");
    await row(wrapper, "OH2ZWC")?.trigger("click");
    expect(cards(wrapper)).toEqual(["OH2ZWC"]);
    await row(wrapper, "OH2ZWC")?.find("button[aria-label='Forget OH2ZWC']").trigger("click");
    expect(socket.sent).not.toContainEqual({ cmd: "forget_station", call: "OH2ZWC" });
    await row(wrapper, "OH2ZWC")?.find("button[aria-label='Really forget OH2ZWC?']").trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "forget_station", call: "OH2ZWC" });
    expect(cards(wrapper)).toEqual([]);
  });

  it("has Close all when there is more than one card, which closes them all, and each card its own cross", async () => {
    const { wrapper } = await open(1400, 900);
    await row(wrapper, "OH2ZWA")?.trigger("click");
    expect(wrapper.find(".cards-closeall").exists()).toBe(false);
    await row(wrapper, "OH2ZWB")?.trigger("click", { ctrlKey: true });
    await row(wrapper, "OH2ZWC")?.trigger("click", { ctrlKey: true });
    await wrapper.findAll(".card")[1]?.find("button[aria-label='Close']").trigger("click");
    expect(cards(wrapper)).toEqual(["OH2ZWA", "OH2ZWC"]);
    await wrapper.find(".cards-closeall").trigger("click");
    expect(wrapper.find(".cardstack").exists()).toBe(false);
    expect(marked()).toEqual([]);
  });

  it("closes all the cards at once with Esc, and not while a field has text in it", async () => {
    const { wrapper } = await open(1400, 900);
    for (const call of ["OH2ZWA", "OH2ZWB", "OH2ZWC"]) await row(wrapper, call)?.trigger("click", { ctrlKey: true });
    await wrapper.find("input[type='search']").setValue("ZW");
    const filter = wrapper.find("input[type='search']").element;
    filter.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    await nextTick();
    expect((filter as HTMLInputElement).value).toBe(""); // (the first Esc is for the text of the box)
    expect(cards(wrapper)).toEqual(["OH2ZWA", "OH2ZWB", "OH2ZWC"]);
    esc();
    await nextTick();
    expect(wrapper.find(".cardstack").exists()).toBe(false);
    expect(marked()).toEqual([]);
    expect(wrapper.findAll("#pane-stations tr.selected")).toHaveLength(0);
  });

  it("deselects with Esc on the Stations tab, with the focus on a row of the table: the cards close and the rows and the markers are not marked", async () => {
    const { wrapper } = await open(1400, 900);
    await row(wrapper, "OH2ZWA")?.trigger("click");
    await row(wrapper, "OH2ZWB")?.trigger("click", { ctrlKey: true });
    const focused = row(wrapper, "OH2ZWB")?.element as HTMLElement;
    focused.focus();
    focused.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    await nextTick();
    expect(wrapper.find(".cardstack").exists()).toBe(false);
    expect(wrapper.findAll("#pane-stations tr.selected")).toHaveLength(0);
    expect(marked()).toEqual([]);
  });

  it("clears the text of the filter box with the first Esc, and deselects with the next", async () => {
    const { wrapper } = await open(1400, 900);
    await row(wrapper, "OH2ZWA")?.trigger("click");
    const box = wrapper.find("#pane-stations input[type='search']");
    await box.setValue("ZWA");
    const press = () => box.element.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    press();
    await nextTick();
    expect((box.element as HTMLInputElement).value).toBe("");
    expect(cards(wrapper)).toEqual(["OH2ZWA"]);
    press();
    await nextTick();
    expect(wrapper.find(".cardstack").exists()).toBe(false);
  });

  it("leaves the first-run guide the Esc key", async () => {
    const { wrapper } = await open(1400, 900, "");
    expect(wrapper.find(".setup").exists()).toBe(true);
    await row(wrapper, "OH2ZWA")?.trigger("click");
    esc();
    await nextTick();
    expect(wrapper.find(".setup").exists()).toBe(false);
    expect(cards(wrapper)).toEqual(["OH2ZWA"]);
    esc();
    await nextTick();
    expect(cards(wrapper)).toEqual([]);
  });
});

describe("station cards on a tablet and a phone", () => {
  it("has two cards at the most on a tablet, in both turns of it", async () => {
    for (const [w, h] of [
      [768, 1024],
      [1024, 768],
    ] as const) {
      const { wrapper } = await open(w, h);
      expect(root(wrapper)).toContain("size-tablet");
      for (const call of CALLS.slice(0, 3)) await row(wrapper, call)?.trigger("click", { ctrlKey: true });
      expect(cards(wrapper)).toEqual(["OH2ZWB", "OH2ZWC"]);
      wrapper.unmount();
      FakeSocket.all = [];
    }
  });

  it("has one card on a phone: a tap, with or without Ctrl, replaces it, and it is a sheet", async () => {
    const { wrapper } = await open(390, 844);
    expect(root(wrapper)).toContain("size-phone");
    marker("OH2ZWA")?.element.click();
    ctrl("OH2ZWB");
    await nextTick();
    expect(cards(wrapper)).toEqual(["OH2ZWB"]);
    expect(wrapper.find(".cardstack").classes()).toContain("sheet");
    expect(wrapper.find(".cards-closeall").exists()).toBe(false);
  });

  it("has one card in a phone held sideways (844 by 390), too", async () => {
    const { wrapper } = await open(844, 390);
    expect(root(wrapper)).toContain("size-phone");
    for (const call of ["OH2ZWA", "OH2ZWB"]) await row(wrapper, call)?.trigger("click", { ctrlKey: true });
    expect(cards(wrapper)).toEqual(["OH2ZWB"]);
  });
});

describe("what a phone shows", () => {
  const panelOn = (wrapper: VueWrapper) =>
    wrapper
      .findAll("[role='tabpanel']")
      .filter((p) => (p.element as HTMLElement).style.display !== "none")
      .map((p) => p.attributes("id"));

  it("starts on the map, with the tab bar over it, and the Map button marked", async () => {
    const { wrapper } = await open(390, 844);
    expect(root(wrapper)).toContain("view-map");
    expect(panelOn(wrapper)).toEqual([]);
    expect(wrapper.find(".tab-map").attributes("aria-pressed")).toBe("true");
  });

  it("brings the open tab with a tab of the bar and the map with the Map button, and remembers where it was left", async () => {
    const { wrapper } = await open(390, 844);
    await wrapper.find("#tab-packets").trigger("click");
    expect(root(wrapper)).toContain("view-panel");
    expect(panelOn(wrapper)).toEqual(["pane-packets"]);
    await wrapper.find(".tab-map").trigger("click");
    expect(root(wrapper)).toContain("view-map");
    expect(panelOn(wrapper)).toEqual([]);
    await wrapper.find("#tab-settings").trigger("click");
    expect(localStorage.getItem("NeoAPRS.view")).toBe("panel");
    expect(localStorage.getItem("NeoAPRS.tab")).toBe("settings");
  });

  it("shows the map with the card when a row of the table is tapped, and the tab again with its bar", async () => {
    const { wrapper } = await open(390, 844);
    await wrapper.find("#tab-stations").trigger("click");
    await row(wrapper, "OH2ZWC")?.trigger("click");
    expect(root(wrapper)).toContain("view-map");
    expect(cards(wrapper)).toEqual(["OH2ZWC"]);
    expect(FakeMap.last().flights.length).toBeGreaterThan(0);
    await wrapper.find("#tab-stations").trigger("click");
    expect(root(wrapper)).toContain("view-panel");
    expect(panelOn(wrapper)).toEqual(["pane-stations"]);
  });

  it("brings the panel when the page asks for a tab: the Message button of a card, the unread mail of the header", async () => {
    const { wrapper } = await open(390, 844);
    marker("OH2ZWA")?.element.click();
    await nextTick();
    await wrapper
      .findAll(".card .btn")
      .find((b) => b.text() === "Message")
      ?.trigger("click");
    expect(root(wrapper)).toContain("view-panel");
    expect(panelOn(wrapper)).toEqual(["pane-messages"]);
  });

  it("goes straight into the conversation from the speech bubble of a row of the Stations table, on a phone", async () => {
    const { wrapper } = await open(390, 844);
    await wrapper.find("#tab-stations").trigger("click");
    await row(wrapper, "OH2ZWB")?.find("button[aria-label='Message OH2ZWB']").trigger("click");
    await flushPromises();
    expect(root(wrapper)).toContain("view-panel");
    expect(panelOn(wrapper)).toEqual(["pane-messages"]);
    expect(wrapper.find("#pane-messages").text()).toContain("OH2ZWB");
    expect(wrapper.find("#pane-messages .convo-back").exists()).toBe(true);
    expect(cards(wrapper)).toEqual([]);
  });

  it("goes to the map to pick a place, and comes back to the tab with the place filled in", async () => {
    const { wrapper } = await open(390, 844);
    await wrapper.find("#tab-beacon").trigger("click");
    await wrapper
      .findAll("#pane-beacon .btn")
      .find((b) => b.text() === "Choose on map")
      ?.trigger("click");
    expect(root(wrapper)).toContain("view-map");
    expect(wrapper.find(".pickbar").exists()).toBe(true);
    FakeMap.last().fire("click", { lngLat: { lat: 60.1234, lng: 24.9876 } });
    await flushPromises();
    expect(root(wrapper)).toContain("view-panel");
    expect(panelOn(wrapper)).toEqual(["pane-beacon"]);
    expect(wrapper.find(".pickbar").exists()).toBe(false);
    await wrapper.find("#pane-beacon .location-place").trigger("click");
    expect((wrapper.find("#set-station-lat").element as HTMLInputElement).value).toBe("60.1234");
  });

  it("goes to the map to pick a place for an object, and its Cancel brings the tab back", async () => {
    const { wrapper } = await open(390, 844);
    await wrapper.find("#tab-objects").trigger("click");
    await wrapper
      .findAll("#pane-objects .btn")
      .find((b) => b.text() === "Choose on map")
      ?.trigger("click");
    expect(root(wrapper)).toContain("view-map");
    await wrapper.find(".pickbar .btn").trigger("click");
    await flushPromises();
    expect(root(wrapper)).toContain("view-panel");
    expect(wrapper.find(".pickbar").exists()).toBe(false);
  });

  it("shows the guide on the whole screen, with the map under it, and the tab as it was when the guide is closed", async () => {
    const { wrapper } = await open(390, 844, "");
    expect(wrapper.find(".setup").exists()).toBe(true);
    expect(root(wrapper)).toEqual(expect.arrayContaining(["guide-open", "view-map"]));
    await wrapper.find(".setup-close").trigger("click");
    expect(root(wrapper)).not.toContain("guide-open");
    await wrapper.find("#tab-stations").trigger("click");
    expect(root(wrapper)).toContain("view-panel");
  });

  it("does not hide the map or the panel on a tablet or a desktop", async () => {
    const { wrapper } = await open(768, 1024);
    expect(root(wrapper)).toContain("size-tablet");
    expect(root(wrapper).some((c) => c.startsWith("view-"))).toBe(false);
    expect(wrapper.find(".tab-map").exists()).toBe(false);
    expect(wrapper.find(".stationmap").exists()).toBe(true);
  });

  it("changes from a phone to a tablet and back when the window is turned, keeping the tab", async () => {
    const { wrapper } = await open(390, 844);
    await wrapper.find("#tab-packets").trigger("click");
    resize(768, 1024);
    await nextTick();
    expect(root(wrapper)).toContain("size-tablet");
    expect(wrapper.find("[aria-selected='true']").text()).toBe("Packets");
    resize(390, 844);
    await nextTick();
    expect(root(wrapper)).toContain("size-phone");
    expect(wrapper.find("[aria-selected='true']").text()).toBe("Packets");
  });
});

describe("the footer under the panel", () => {
  const foot = (wrapper: VueWrapper) => wrapper.find(".panelfoot");
  const panelOn = (wrapper: VueWrapper) =>
    wrapper
      .findAll("[role='tabpanel']")
      .filter((p) => (p.element as HTMLElement).style.display !== "none")
      .map((p) => p.attributes("id"));

  it("is under the open tab on a phone, and not on the map's turn", async () => {
    const { wrapper } = await open(390, 844);
    await wrapper.find("#tab-stations").trigger("click");
    expect(root(wrapper)).toContain("view-panel");
    expect(foot(wrapper).exists()).toBe(true);
    expect(foot(wrapper).text()).toContain("NeoAPRS");
    expect(wrapper.find(".panel-body").element.lastElementChild).toBe(foot(wrapper).element);
    await wrapper.find(".tab-map").trigger("click");
    expect(root(wrapper)).toContain("view-map");
    expect(foot(wrapper).exists()).toBe(false);
    expect(wrapper.find(".mapwrap .panelfoot").exists()).toBe(false);
    await wrapper.find("#tab-stations").trigger("click");
    expect(foot(wrapper).exists()).toBe(true);
  });

  it("is under the panel and not under the map on a tablet and a desktop", async () => {
    for (const [width, height] of [
      [768, 1024],
      [1440, 900],
    ] as const) {
      const { wrapper } = await open(width, height);
      expect(wrapper.find(".panel .panelfoot").exists()).toBe(true);
      expect(wrapper.findAll(".panelfoot")).toHaveLength(1);
      expect(wrapper.find(".mapwrap .panelfoot").exists()).toBe(false);
      wrapper.unmount();
      FakeSocket.all = [];
    }
  });

  it("goes with a folded panel (nothing but its handle is left) and is back with it", async () => {
    const { wrapper } = await open(1440, 900);
    await wrapper.find(".panel-fold").trigger("click");
    expect(foot(wrapper).exists()).toBe(false);
    await wrapper.find(".panel-fold").trigger("click");
    expect(foot(wrapper).exists()).toBe(true);
  });

  it("has the whole Update to 0.6.1 on a phone, which opens the steps of the update", async () => {
    const { wrapper, socket } = await open(390, 844);
    await wrapper.find("#tab-stations").trigger("click");
    socket.say(status({ update: { version: "0.6.1", url: "", message: "" } }));
    await flushPromises();
    expect(foot(wrapper).find("button.update").text()).toBe("Update to 0.6.1");
    await foot(wrapper).find("button.update").trigger("click");
    expect(wrapper.find(".updatedialog h2").text()).toBe("NeoAPRS 0.6.1 is available");
  });

  it("shows a newer version on a phone's map, which has no footer, as a badge of the header that opens the dialog", async () => {
    const { wrapper, socket } = await open(390, 844);
    expect(wrapper.find(".headupdate").exists()).toBe(false);
    socket.say(status({ update: { version: "0.6.1", url: "", message: "" } }));
    await flushPromises();
    expect(foot(wrapper).exists()).toBe(false);
    const badge = wrapper.find(".appheader button.headupdate");
    expect(badge.text()).toContain("0.6.1");
    expect(badge.attributes("title")).toBe("NeoAPRS 0.6.1 is available");
    await badge.trigger("click");
    expect(wrapper.find(".updatedialog h2").text()).toBe("NeoAPRS 0.6.1 is available");
  });

  it("has no badge of the update in the header of a desktop, whose footer shows it", async () => {
    const { wrapper, socket } = await open(1440, 900);
    socket.say(status({ update: { version: "0.6.1", url: "", message: "" } }));
    await flushPromises();
    expect(wrapper.find(".headupdate").exists()).toBe(false);
    expect(foot(wrapper).find("button.update").text()).toBe("Update to 0.6.1");
  });

  it("has the radio message on a phone that opens the Settings tab", async () => {
    const { wrapper, socket } = await open(390, 844);
    await wrapper.find("#tab-stations").trigger("click");
    socket.say({ type: "state", topic: "tnc", rev: 1, value: tncState({ state: "silent", problem: "", describe: "silent", silent_since: ago(600) }) });
    await flushPromises();
    expect(foot(wrapper).find("button.status").text()).toBe("Radio: silent");
    await foot(wrapper).find("button.status").trigger("click");
    expect(panelOn(wrapper)).toEqual(["pane-settings"]);
  });
});

describe("the default width of the panel", () => {
  it("is 760 px on a window of 1280 px and more, 480 px on a smaller one, and the user's own width when it was dragged", async () => {
    const wide = await open(1440, 900);
    expect(wide.wrapper.find(".panel").attributes("style")).toContain("--panel-width: 760px");
    wide.wrapper.unmount();
    FakeSocket.all = [];
    const small = await open(1200, 800);
    expect(small.wrapper.find(".panel").attributes("style")).toContain("--panel-width: 480px");
    small.wrapper.unmount();
    FakeSocket.all = [];
    localStorage.setItem("NeoAPRS.panelwidth", "520");
    const dragged = await open(1440, 900);
    expect(dragged.wrapper.find(".panel").attributes("style")).toContain("--panel-width: 520px");
  });
});
