import "@/test/mockmap";
import { describe, expect, it, vi } from "vitest";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { ANSWER_MS } from "@/composables/useSettingsQueue";
import { FIRST_DELAY_MS } from "@/lib/hub";
import { FakeSocket } from "@/test/fakesocket";
import { NOW, configValues, errorOf, gpsState, hello, igateState } from "@/test/fixtures";
import { open, switchFace, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

const KEY = "station/transmit";
const say = async (socket: FakeSocket, rev: number, values: Record<string, string>) => {
  socket.say({ type: "state", topic: "config", rev, value: configValues(values) });
  await flushPromises();
};
const sets = (socket: FakeSocket) => socket.sent.filter((c) => (c as { cmd: string }).cmd === "set_config");
const press = async (wrapper: VueWrapper) => {
  await wrapper.find(".appheader #rx-switch").trigger("click");
  await flushPromises();
};
/** The press that confirms sure?: the switch ignores one sooner than 500 ms after the arming press. */
const pressAgain = async (wrapper: VueWrapper) => {
  const later = Date.now() + 600;
  const now = vi.spyOn(Date, "now").mockReturnValue(later);
  await press(wrapper);
  now.mockRestore();
};
const fakeTimeouts = () => vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout"], now: NOW });

describe("App: the RX only switch", () => {
  it("switches to RX only from any tab with one press and back with two", async () => {
    const { wrapper, socket } = await open();
    let rev = 1;
    for (const tab of ["Stations", "Messages", "Settings"]) {
      await tabButton(wrapper, tab)?.trigger("click");
      expect(switchFace(wrapper), tab).toBe("RX + TX");
      await press(wrapper);
      expect(sets(socket).at(-1), tab).toEqual({ cmd: "set_config", values: { [KEY]: "false" } });
      // before the daemon's answer
      expect(switchFace(wrapper), tab).toBe("RX only");
      await say(socket, rev++, { [KEY]: "false" });
      const before = sets(socket).length;
      await press(wrapper);
      expect(switchFace(wrapper), tab).toBe("sure?");
      expect(sets(socket), tab).toHaveLength(before);
      await pressAgain(wrapper);
      expect(sets(socket).at(-1), tab).toEqual({ cmd: "set_config", values: { [KEY]: "true" } });
      await say(socket, rev++, { [KEY]: "true" });
      expect(switchFace(wrapper), tab).toBe("RX + TX");
    }
  });

  it("has no RX only tickbox in Settings → Radio, and none on the My station tab", async () => {
    const { wrapper } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const radio = wrapper.findAll("#pane-settings fieldset").find((f) => f.find("legend").text() === "Radio");
    expect(radio?.find(".group-body").element.firstElementChild?.matches("fieldset.subbox")).toBe(true);
    expect(wrapper.find("#set-station-transmit").exists()).toBe(false);
    await tabButton(wrapper, "My station")?.trigger("click");
    expect(wrapper.find("#pane-beacon").text()).not.toContain("RX only");
  });

  it("is told by the daemon to every open page: a press on one page sends from it alone, and another page's sure? goes", async () => {
    const a = await open();
    const b = await open();
    expect(a.socket).toBe(FakeSocket.all[0]);
    const both = async (rev: number, values: Record<string, string>) => {
      await say(a.socket, rev, values);
      await say(b.socket, rev, values);
    };
    await press(a.wrapper);
    expect(sets(a.socket)).toEqual([{ cmd: "set_config", values: { [KEY]: "false" } }]);
    expect(sets(b.socket)).toEqual([]);
    expect(switchFace(b.wrapper)).toBe("RX + TX");
    await both(1, { [KEY]: "false" });
    expect([switchFace(a.wrapper), switchFace(b.wrapper)]).toEqual(["RX only", "RX only"]);
    await press(b.wrapper);
    expect(switchFace(b.wrapper)).toBe("sure?");
    await press(a.wrapper);
    await pressAgain(a.wrapper);
    expect(sets(a.socket).at(-1)).toEqual({ cmd: "set_config", values: { [KEY]: "true" } });
    await both(2, { [KEY]: "true" });
    expect(switchFace(b.wrapper)).toBe("RX + TX");
    await both(3, { [KEY]: "false" });
    // disarmed: B's next press asks again and sends nothing
    expect(switchFace(b.wrapper)).toBe("RX only");
    await press(b.wrapper);
    expect(sets(b.socket)).toEqual([]);
  });

  it("is disabled with the offline title and keeps its face while the socket is closed, and works once it is open again", async () => {
    const { wrapper, socket } = await open();
    fakeTimeouts();
    socket.hangUp();
    await flushPromises();
    const button = wrapper.find(".appheader #rx-switch");
    expect(button.attributes("disabled")).toBeDefined();
    expect(button.attributes("title")).toBe("NeoAPRS does not answer. The page connects again by itself");
    expect(switchFace(wrapper)).toBe("RX + TX");
    await press(wrapper);
    expect(sets(socket)).toEqual([]);
    vi.advanceTimersByTime(FIRST_DELAY_MS);
    const again = FakeSocket.last();
    expect(again).not.toBe(socket);
    again.say(hello());
    again.say({ type: "state", topic: "config", rev: 0, value: configValues() });
    await flushPromises();
    expect(wrapper.find(".appheader #rx-switch").attributes("disabled")).toBeUndefined();
    await press(wrapper);
    expect(sets(again)).toEqual([{ cmd: "set_config", values: { [KEY]: "false" } }]);
  });

  it("goes after a field of the Settings tab that was typed in and left, and leaves a field still being typed in as it is", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const field = () => wrapper.find<HTMLInputElement>("#pane-settings #set-map-radius_km");
    await field().setValue("200");
    await field().trigger("blur");
    await press(wrapper);
    expect(sets(socket)).toEqual([{ cmd: "set_config", values: { "map/radius_km": "200" } }]);
    await say(socket, 1, { "map/radius_km": "200" });
    expect(sets(socket).at(-1)).toEqual({ cmd: "set_config", values: { [KEY]: "false" } });
    await say(socket, 2, { "map/radius_km": "200", [KEY]: "false" });
    // a text that is not valid stays with its error, and only the switch's request goes
    await field().setValue("5");
    await field().trigger("blur");
    const before = sets(socket).length;
    await press(wrapper);
    await pressAgain(wrapper);
    expect(sets(socket).slice(before)).toEqual([{ cmd: "set_config", values: { [KEY]: "true" } }]);
    expect(field().element.value).toBe("5");
    expect(field().element.closest(".field")?.querySelector(".field-error")?.textContent ?? "").not.toBe("");
    await say(socket, 3, { "map/radius_km": "200" });
    // still being typed in
    await field().setValue("250");
    const typed = sets(socket).length;
    await press(wrapper);
    expect(sets(socket).slice(typed)).toEqual([{ cmd: "set_config", values: { [KEY]: "false" } }]);
    await say(socket, 4, { "map/radius_km": "200", [KEY]: "false" });
    expect(field().element.value).toBe("250");
  });

  it("sends RX only next while a save is out, ahead of the saves waiting; transmitting again keeps its place", async () => {
    const { wrapper, socket } = await open();
    const pane = (id: string) => (id === "station-comment" ? ["My station", "beacon"] : ["Settings", "settings"]);
    const field = (id: string) => wrapper.find<HTMLInputElement>(`#pane-${pane(id)[1]} #set-${id}`);
    const commit = async (id: string, text: string) => {
      await tabButton(wrapper, pane(id)[0] ?? "")?.trigger("click");
      await field(id).setValue(text);
      await field(id).trigger("blur");
    };
    await commit("map-radius_km", "200");
    await commit("station-comment", "out and in");
    await press(wrapper);
    expect(sets(socket)).toEqual([{ cmd: "set_config", values: { "map/radius_km": "200" } }]);
    await say(socket, 1, { "map/radius_km": "200" });
    expect(sets(socket).at(-1)).toEqual({ cmd: "set_config", values: { [KEY]: "false" } });
    await say(socket, 2, { "map/radius_km": "200", [KEY]: "false" });
    expect(sets(socket).at(-1)).toEqual({ cmd: "set_config", values: { "station/comment": "out and in" } });
    await say(socket, 3, { "map/radius_km": "200", [KEY]: "false", "station/comment": "out and in" });
    expect(field("station-comment").element.value).toBe("out and in");
    await tabButton(wrapper, "Settings")?.trigger("click");
    expect(field("map-radius_km").element.value).toBe("200");
    // the comment is greyed while RX only is on, so the waiting save is the radius again
    await commit("map-radius_km", "250");
    await commit("map-radius_km", "260");
    await press(wrapper);
    await pressAgain(wrapper);
    await say(socket, 4, { "map/radius_km": "250", [KEY]: "false", "station/comment": "out and in" });
    expect(sets(socket).at(-1)).toEqual({ cmd: "set_config", values: { "map/radius_km": "260" } });
    await say(socket, 5, { "map/radius_km": "260", [KEY]: "false", "station/comment": "out and in" });
    expect(sets(socket).at(-1)).toEqual({ cmd: "set_config", values: { [KEY]: "true" } });
    expect(field("map-radius_km").element.value).toBe("260");
  });

  it("puts the face back after a refused or unanswered save, with no toast, and the buttons that send follow it", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "My station")?.trigger("click");
    const now = () => wrapper.find<HTMLButtonElement>("#pane-beacon #beacon-now").element;
    expect(now().disabled).toBe(false);
    await press(wrapper);
    // RX only at once, before the daemon has answered
    expect([now().disabled, now().title]).toEqual([true, "RX only: nothing is sent"]);
    await tabButton(wrapper, "Messages")?.trigger("click");
    await wrapper.find("#pane-messages .conv").trigger("click");
    await wrapper.find("#msg-text").setValue("Hello");
    const send = () => wrapper.find<HTMLButtonElement>("#pane-messages button[type=submit]").element;
    expect(send().disabled).toBe(true);
    socket.say(errorOf("set_config: station/transmit: the database is busy", "failed"));
    await flushPromises();
    expect(switchFace(wrapper)).toBe("RX + TX");
    expect(wrapper.find(".toast").exists()).toBe(false);
    expect(send().disabled).toBe(false);
    await tabButton(wrapper, "My station")?.trigger("click");
    expect(now().disabled).toBe(false);
    fakeTimeouts();
    await press(wrapper);
    expect(switchFace(wrapper)).toBe("RX only");
    vi.advanceTimersByTime(ANSWER_MS);
    await flushPromises();
    expect(switchFace(wrapper)).toBe("RX + TX");
    expect(wrapper.find(".toast").exists()).toBe(false);
  });

  it("is last in the header on a phone, outside the marks, and works from the map and from a tab", async () => {
    window.innerWidth = 390;
    window.innerHeight = 844;
    window.dispatchEvent(new Event("resize"));
    const { wrapper, socket } = await open();
    expect(wrapper.find(".app").classes()).toContain("size-phone");
    const header = wrapper.find(".appheader").element;
    expect(header.lastElementChild?.id).toBe("rx-switch");
    expect(wrapper.find(".headpills #rx-switch").exists()).toBe(false);
    await wrapper.find(".tab-map").trigger("click");
    expect(wrapper.find(".app").classes()).toContain("view-map");
    await press(wrapper);
    expect(sets(socket).at(-1)).toEqual({ cmd: "set_config", values: { [KEY]: "false" } });
    await say(socket, 1, { [KEY]: "false" });
    await tabButton(wrapper, "Messages")?.trigger("click");
    expect(wrapper.find(".app").classes()).toContain("view-panel");
    await press(wrapper);
    await pressAgain(wrapper);
    expect(sets(socket).at(-1)).toEqual({ cmd: "set_config", values: { [KEY]: "true" } });
  });

  it("moves nothing: the switch is the same element and the marks the same, with the beacon on and off", async () => {
    for (const beacon of ["30", "0"]) {
      const { wrapper, socket } = await open();
      await say(socket, 1, { "beacon/interval_min": beacon });
      const element = wrapper.find("#rx-switch").element;
      const marks = () => wrapper.findAll(".appheader .headpills .tag").map((m) => m.text());
      const before = marks();
      expect(before.includes("Beacon off"), beacon).toBe(beacon === "0");
      await press(wrapper);
      await say(socket, 2, { "beacon/interval_min": beacon, [KEY]: "false" });
      await press(wrapper);
      expect(switchFace(wrapper)).toBe("sure?");
      expect(wrapper.find("#rx-switch").element).toBe(element);
      expect(marks(), beacon).toEqual(before);
      wrapper.unmount();
    }
  });
});

describe("App: RX only elsewhere on the page", () => {
  it("opens the My station tab from Beacon off, which shows while RX only is on too", async () => {
    const { wrapper, socket } = await open();
    await say(socket, 1, { [KEY]: "false", "beacon/interval_min": "0" });
    await tabButton(wrapper, "Stations")?.trigger("click");
    expect(wrapper.find(".appheader .pill-beacon_off").text()).toBe("Beacon off");
    expect(wrapper.find(".appheader .pill-beacon_off").classes()).toContain("tag-neutral");
    await wrapper.find(".appheader .pill-beacon_off").trigger("click");
    expect(wrapper.find("[aria-selected='true']").text()).toContain("My station");
  });

  it("brings the group of the control a mark leads to into view, flashes it and focuses the control: GPS and Internet", async () => {
    const scrolled = vi.fn();
    Element.prototype.scrollIntoView = scrolled;
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "igate", rev: 1, value: igateState() });
    await say(socket, 1, { [KEY]: "false", "gps/source": "gpsd", "igate/enabled": "true" });
    const marks: [string, string, string][] = [
      [".pill-gps", "set-gps-source", "Station"],
      [".pill-internet", "set-igate-enabled", "Internet (APRS-IS)"],
    ];
    for (const [mark, control, legend] of marks) {
      scrolled.mockClear();
      await wrapper.find(`.appheader ${mark}`).trigger("click");
      await vi.waitFor(() =>
        expect(document.getElementById(control)?.closest("fieldset")?.classList.contains("attend"), mark).toBe(true),
      );
      const group = document.getElementById(control)?.closest("fieldset");
      expect(group?.querySelector("legend")?.textContent?.replace(/\s*i$/, "").trim(), mark).toBe(legend);
      expect(scrolled.mock.contexts, mark).toContain(group);
      expect(document.activeElement?.id, mark).toBe(control);
    }
  });

  it("has the Internet mark while the Internet group is connected, and the GPS mark mint with a fix and on the warn plate without, all before the count", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "igate", rev: 1, value: igateState() });
    await say(socket, 1, { "gps/source": "gpsd" });
    socket.say({ type: "state", topic: "gps", rev: 1, value: gpsState({ state: "no_fix" }) });
    await flushPromises();
    const marks = wrapper.findAll(".appheader .headpills .tag");
    expect(marks.map((m) => m.text())).toEqual(["NeoAPRS", "Packet", "GPS", "Internet"]);
    expect(marks[2]?.classes()).toContain("tag-warn");
    socket.say({ type: "state", topic: "gps", rev: 2, value: gpsState({ state: "fix" }) });
    await flushPromises();
    expect(wrapper.find(".appheader .pill-gps").classes()).toContain("tag-ok");
    expect(wrapper.find(".appheader .headpills").element.nextElementSibling?.classList.contains("headmail")).toBe(true);
  });

  it("greys the beacon's fields as with Beacon Off and turns every button that sends off with the title RX only: nothing is sent", async () => {
    const { wrapper, socket } = await open();
    await say(socket, 1, { [KEY]: "false" });
    await tabButton(wrapper, "My station")?.trigger("click");
    for (const id of ["#set-station-comment", "#set-beacon-travel", "#set-beacon-path"]) {
      const field = wrapper.find(id);
      if (field.exists()) expect((field.element as HTMLInputElement).disabled, id).toBe(true);
    }
    const now = wrapper.find("#pane-beacon #beacon-now").element as HTMLButtonElement;
    expect(now.disabled).toBe(true);
    expect(now.title).toBe("RX only: nothing is sent");
    await tabButton(wrapper, "Messages")?.trigger("click");
    await wrapper.find("#pane-messages .convlist button, #pane-messages .conv").trigger("click");
    const send = wrapper.find("#pane-messages button[type=submit]");
    if (send.exists()) expect(send.attributes("disabled")).toBeDefined();
    await tabButton(wrapper, "Bulletins")?.trigger("click");
    expect(wrapper.find("#pane-bulletins button[type=submit]").attributes("title")).toBe("RX only: nothing is sent");
    await tabButton(wrapper, "Objects")?.trigger("click");
    expect(wrapper.find("#pane-objects form button[type=submit]").attributes("title")).toBe("RX only: nothing is sent");
    await say(socket, 2, { [KEY]: "true" });
    // A new object has no place until one is picked.
    expect(wrapper.find("#pane-objects form button[type=submit]").attributes("title")).toBe("Choose a place first");
  });

  it("says the beacon is off in the toast when the daemon refuses Beacon now for that, and the daemon's RX only refusal in the page's words", async () => {
    const { wrapper, socket } = await open();
    socket.say({
      type: "error",
      text: "beacon_now: nothing was sent: the beacon is off",
      code: "beacon.not_sent",
      params: { reason: "the beacon is off" },
    });
    await flushPromises();
    expect(wrapper.text()).toContain("nothing was sent: the beacon is off");
    socket.say({
      type: "error",
      text: "beacon_now: receive only: transmitting is switched off",
      code: "transmit.off",
      params: {},
    });
    await flushPromises();
    expect(wrapper.text()).toContain("RX only: nothing is sent");
  });
});

describe("App: a station that an earlier version left in RX only", () => {
  it("opens with the switch on RX only, and two presses send the setting at once", async () => {
    const { wrapper, socket } = await open();
    await say(socket, 1, { [KEY]: "false", "beacon/interval_min": "30" });
    expect(switchFace(wrapper)).toBe("RX only");
    expect(wrapper.find("#rx-switch").classes()).toContain("tag-warn");
    expect(wrapper.find("#rx-switch").attributes("title")).toBe("Nothing is sent");
    await press(wrapper);
    await pressAgain(wrapper);
    expect(socket.sent).toContainEqual({ cmd: "set_config", values: { [KEY]: "true" } });
    await say(socket, 2, { [KEY]: "true", "beacon/interval_min": "30" });
    expect(switchFace(wrapper)).toBe("RX + TX");
    await tabButton(wrapper, "My station")?.trigger("click");
    expect((wrapper.find("#pane-beacon #beacon-now").element as HTMLButtonElement).disabled).toBe(false);
  });
});
