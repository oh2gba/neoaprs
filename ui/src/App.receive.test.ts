import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { configValues } from "@/test/fixtures";
import { open, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

const KEY = "station/transmit";

describe("App: Receive only", () => {
  it("has the Transmit switch first in the Station group of the Beacon tab, On by default, and a change applies at once", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Beacon")?.trigger("click");
    const station = wrapper.find("#pane-beacon fieldset");
    expect(station.find("legend").text()).toBe("Station");
    const first = station.find(".field");
    expect(first.find("label").text()).toBe("Transmit");
    const select = first.find("select");
    expect(select.attributes("id")).toBe("set-station-transmit");
    expect(select.findAll("option").map((o) => o.text())).toEqual(["On", "Receive only"]);
    expect((select.element as HTMLSelectElement).value).toBe("true");
    await select.setValue("false");
    expect(socket.sent).toContainEqual({ cmd: "set_config", values: { [KEY]: "false" } });
    expect(wrapper.find("#pane-settings #set-station-transmit").exists()).toBe(false);
  });

  it("shows an amber Receive only badge beside the title while transmitting is off, and none while it is on", async () => {
    const { wrapper, socket } = await open();
    expect(wrapper.find(".appheader .rxonly").exists()).toBe(false);
    socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ [KEY]: "false" }) });
    await flushPromises();
    const badge = wrapper.find(".appheader .rxonly");
    expect(badge.text()).toBe("Receive only");
    expect(badge.element.previousElementSibling?.tagName).toBe("H1");
    socket.say({ type: "state", topic: "config", rev: 2, value: configValues({ [KEY]: "true" }) });
    await flushPromises();
    expect(wrapper.find(".appheader .rxonly").exists()).toBe(false);
  });

  it("opens the Beacon tab from the badge, and leaves the buttons and the footer as they are", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ [KEY]: "false" }) });
    await flushPromises();
    await tabButton(wrapper, "Stations")?.trigger("click");
    await wrapper.find(".appheader .rxonly").trigger("click");
    expect(wrapper.find("[aria-selected='true']").text()).toContain("Beacon");
    expect((wrapper.find("#pane-beacon .sendrow button").element as HTMLButtonElement).disabled).toBe(false);
    expect(wrapper.find(".panelfoot").text()).not.toMatch(/receive only/i);
    expect(wrapper.find("#pane-beacon #set-station-transmit").exists()).toBe(true);
    await wrapper.find("#pane-beacon .sendrow button").trigger("click");
    await wrapper.find("#pane-beacon .sendrow button").trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "beacon_now" });
  });

  it("says the daemon's refusal in the toast, in the page's words", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "error", text: "beacon_now: receive only: transmitting is switched off", code: "transmit.off", params: {} });
    await flushPromises();
    expect(wrapper.text()).toContain("Receive only: nothing is sent");
  });
});
