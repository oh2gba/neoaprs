import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { configValues } from "@/test/fixtures";
import { open, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

const KEY = "station/transmit";

describe("App: Receive only", () => {
  it("has no Transmit switch: the Beacon tab starts with the call, the Settings tab has none, and a station set to receive only is not changed from the page", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Beacon")?.trigger("click");
    const station = wrapper.find("#pane-beacon fieldset");
    expect(station.find("legend").text()).toBe("Station");
    expect(station.find(".field label").text()).toBe("Call");
    for (const value of ["true", "false"]) {
      socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ [KEY]: value }) });
      await flushPromises();
      expect(wrapper.find("#set-station-transmit").exists(), value).toBe(false);
      expect(wrapper.find("#pane-beacon").text(), value).not.toContain("Transmit");
      expect(wrapper.find("#pane-settings").text(), value).not.toContain("Transmit");
    }
    expect(socket.sent.filter((m) => JSON.stringify(m).includes(KEY))).toEqual([]);
  });

  it("shows an amber Receive only badge beside the title while transmitting is off, and none while it is on", async () => {
    const { wrapper, socket } = await open();
    expect(wrapper.find(".appheader .rxonly").exists()).toBe(false);
    socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ [KEY]: "false" }) });
    await flushPromises();
    const badge = wrapper.find(".appheader .rxonly");
    expect(badge.text()).toBe("Receive only");
    expect(badge.element.previousElementSibling?.tagName).toBe("H1");
    expect(badge.attributes("title")).toBe("Nothing is transmitted: this station is set to receive only");
    socket.say({ type: "state", topic: "config", rev: 2, value: configValues({ [KEY]: "true" }) });
    await flushPromises();
    expect(wrapper.find(".appheader .rxonly").exists()).toBe(false);
  });

  it("opens the Beacon tab from the badge, and leaves the buttons and the footer as they are (the beacon being on)", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ [KEY]: "false" }) });
    await flushPromises();
    await tabButton(wrapper, "Stations")?.trigger("click");
    await wrapper.find(".appheader .rxonly").trigger("click");
    expect(wrapper.find("[aria-selected='true']").text()).toContain("Beacon");
    expect((wrapper.find("#pane-beacon .beaconstatus button").element as HTMLButtonElement).disabled).toBe(false);
    expect(wrapper.find(".panelfoot").text()).not.toMatch(/receive only/i);
    expect(wrapper.find("#pane-beacon #set-station-transmit").exists()).toBe(false);
    await wrapper.find("#pane-beacon .beaconstatus button").trigger("click");
    await wrapper.find("#pane-beacon .beaconstatus button").trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "beacon_now" });
  });

  it("does not mark a station whose beacon is Off as receive only: Off is not receive only", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ "beacon/interval_min": "0" }) });
    await flushPromises();
    expect(wrapper.find(".appheader .rxonly").exists()).toBe(false);
    await tabButton(wrapper, "Beacon")?.trigger("click");
    expect(wrapper.find("#pane-beacon .beaconstatus .tncstatus").text()).toBe("Beacon off");
    expect((wrapper.find("#pane-beacon .beaconstatus button").element as HTMLButtonElement).disabled).toBe(true);
  });

  it("says the beacon is off in the toast when the daemon refuses Beacon now for that", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "error", text: "beacon_now: nothing was sent: the beacon is off", code: "beacon.not_sent", params: { reason: "the beacon is off" } });
    await flushPromises();
    expect(wrapper.text()).toContain("nothing was sent: the beacon is off");
  });

  it("says the daemon's refusal in the toast, in the page's words", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "error", text: "beacon_now: receive only: transmitting is switched off", code: "transmit.off", params: {} });
    await flushPromises();
    expect(wrapper.text()).toContain("Receive only: nothing is sent");
  });
});
