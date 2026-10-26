import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { configValues, igateState, gpsState } from "@/test/fixtures";
import { open, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

const KEY = "station/transmit";
const say = async (socket: Awaited<ReturnType<typeof open>>["socket"], rev: number, values: Record<string, string>) => {
  socket.say({ type: "state", topic: "config", rev, value: configValues(values) });
  await flushPromises();
};

describe("App: RX only", () => {
  it("has the RX only tickbox as the first row of the Radio group of the Settings tab, with its (i), and none on the Beacon tab", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const radio = wrapper.findAll("#pane-settings fieldset").find((f) => f.find("legend").text() === "Radio");
    expect(radio?.find(".field label").text()).toBe("RX only");
    expect(radio?.find(".field input").attributes("type")).toBe("checkbox");
    expect((radio?.find(".field input").element as HTMLInputElement).checked).toBe(false); // (unticked: the station transmits)
    expect(radio?.find(".field .infotip").exists()).toBe(true);
    await tabButton(wrapper, "Beacon")?.trigger("click");
    expect(wrapper.find("#pane-beacon").text()).not.toContain("RX only");
    await radio?.find(".field input").setValue(true);
    expect(socket.sent).toContainEqual({ cmd: "set_config", values: { [KEY]: "false" } }); // (ticked: RX only, which is station/transmit false)
  });

  it("shows the amber RX only mark first among the marks, in place of the old badge, while transmitting is off, and none while it is on", async () => {
    const { wrapper, socket } = await open();
    expect(wrapper.find(".appheader .rxonly").exists()).toBe(false);
    await say(socket, 1, { [KEY]: "false" });
    const mark = wrapper.find(".appheader .rxonly");
    expect(mark.text()).toBe("RX only");
    expect(mark.classes()).toContain("tag-warn");
    expect(mark.attributes("title")).toBe("Nothing is sent. Settings → Radio → RX only");
    expect(wrapper.find(".appheader .headpills").element.firstElementChild).toBe(mark.element);
    await say(socket, 2, { [KEY]: "true" });
    expect(wrapper.find(".appheader .rxonly").exists()).toBe(false);
  });

  it("opens the Settings tab from the RX only mark and the Beacon tab from Beacon off", async () => {
    const { wrapper, socket } = await open();
    await say(socket, 1, { [KEY]: "false" });
    await tabButton(wrapper, "Stations")?.trigger("click");
    await wrapper.find(".appheader .rxonly").trigger("click");
    expect(wrapper.find("[aria-selected='true']").text()).toContain("Settings");
    await say(socket, 2, { [KEY]: "true", "beacon/interval_min": "0" });
    expect(wrapper.find(".appheader .pill-beacon_off").text()).toBe("Beacon off");
    expect(wrapper.find(".appheader .pill-beacon_off").classes()).toContain("tag-neutral");
    await wrapper.find(".appheader .pill-beacon_off").trigger("click");
    expect(wrapper.find("[aria-selected='true']").text()).toContain("Beacon");
  });

  it("has the Internet mark while the Internet group is connected, and the GPS mark blue with a fix and amber without, all before the count", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "igate", rev: 1, value: igateState() });
    await say(socket, 1, { "gps/source": "gpsd" });
    socket.say({ type: "state", topic: "gps", rev: 1, value: gpsState({ state: "no_fix" }) });
    await flushPromises();
    const marks = wrapper.findAll(".appheader .headpills .tag");
    expect(marks.map((m) => m.text())).toEqual(["Internet", "GPS"]);
    expect(marks[1]?.classes()).toContain("tag-warn");
    socket.say({ type: "state", topic: "gps", rev: 2, value: gpsState({ state: "fix" }) });
    await flushPromises();
    expect(wrapper.find(".appheader .pill-gps").classes()).toContain("tag-ok");
    expect(wrapper.find(".appheader .headpills").element.nextElementSibling?.classList.contains("headmail")).toBe(true);
  });

  it("greys the beacon's fields as with Beacon Off and turns every button that sends off with the title RX only: nothing is sent", async () => {
    const { wrapper, socket } = await open();
    await say(socket, 1, { [KEY]: "false" });
    await tabButton(wrapper, "Beacon")?.trigger("click");
    for (const id of ["#set-station-comment", "#set-beacon-travel", "#set-beacon-path"]) {
      const field = wrapper.find(id);
      if (field.exists()) expect((field.element as HTMLInputElement).disabled, id).toBe(true);
    }
    const now = wrapper.find("#pane-beacon .beaconstatus button").element as HTMLButtonElement;
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
    expect(wrapper.find("#pane-objects form button[type=submit]").attributes("title") ?? "").toBe("");
  });

  it("says the beacon is off in the toast when the daemon refuses Beacon now for that, and the daemon's RX only refusal in the page's words", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "error", text: "beacon_now: nothing was sent: the beacon is off", code: "beacon.not_sent", params: { reason: "the beacon is off" } });
    await flushPromises();
    expect(wrapper.text()).toContain("nothing was sent: the beacon is off");
    socket.say({ type: "error", text: "beacon_now: receive only: transmitting is switched off", code: "transmit.off", params: {} });
    await flushPromises();
    expect(wrapper.text()).toContain("RX only: nothing is sent");
  });
});

describe("App: a station that an earlier version left in RX only", () => {
  it("opens with the RX only mark and the RX only tickbox ticked in Settings → Radio, and unticking it sends the setting at once", async () => {
    const { wrapper, socket } = await open();
    await say(socket, 1, { [KEY]: "false", "beacon/interval_min": "30" });
    expect(wrapper.find(".appheader .rxonly").text()).toBe("RX only");
    await tabButton(wrapper, "Settings")?.trigger("click");
    const tick = wrapper.find<HTMLInputElement>("#set-station-transmit");
    expect(tick.element.checked).toBe(true);
    await tick.setValue(false);
    expect(socket.sent).toContainEqual({ cmd: "set_config", values: { [KEY]: "true" } }); // (unticked: transmits)
    await say(socket, 2, { [KEY]: "true", "beacon/interval_min": "30" });
    expect(wrapper.find(".appheader .rxonly").exists()).toBe(false);
    await tabButton(wrapper, "Beacon")?.trigger("click");
    expect((wrapper.find("#pane-beacon .beaconstatus button").element as HTMLButtonElement).disabled).toBe(false);
  });
});
