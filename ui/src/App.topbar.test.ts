// The top bar says how things stand (the Daemon mark in a browser, the Radio mark everywhere); a
// text that says RX only leads to the tickbox.
import "@/test/mockmap";
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import type { FakeSocket } from "@/test/fakesocket";
import { configValues } from "@/test/fixtures";
import { open, tabButton, useAppHarness } from "@/test/app";

useAppHarness();
afterEach(() => {
  history.replaceState(null, "", location.pathname);
});

const KEY = "station/transmit";
/**
 * The settings sent again with these, a radio's own (`radio/1/digipeat`) among the radios' values.
 */
const say = async (socket: FakeSocket, rev: number, values: Record<string, string>) => {
  const own = (radio: boolean) =>
    Object.fromEntries(Object.entries(values).filter(([key]) => key.startsWith("radio/") === radio));
  socket.say({ type: "state", topic: "config", rev, value: configValues(own(false), own(true)) });
  await flushPromises();
};
const flashed = (control: string) =>
  document.getElementById(control)?.closest("fieldset")?.classList.contains("attend");

describe("the Daemon mark", () => {
  it("is in a browser, between Update and Radio", async () => {
    const { wrapper } = await open();
    expect(wrapper.findAll(".appheader .headpills .tag").map((m) => m.text())).toEqual(["NeoAPRS", "Radio"]);
  });

  it("is not in the desktop app, whose window loads the page with the fragment #app; the Radio mark is", async () => {
    history.replaceState(null, "", "#app");
    const { wrapper, socket } = await open();
    expect(wrapper.find(".appheader .pill-daemon").exists()).toBe(false);
    expect(wrapper.find(".appheader .pill-radio").text()).toBe("Radio");
    vi.useFakeTimers();
    socket.hangUp();
    await flushPromises();
    vi.useRealTimers();
    expect(wrapper.find(".appheader .pill-daemon").exists()).toBe(false);
    expect(wrapper.find(".appheader .pill-radio").text()).toBe("Radio: waiting…");
  });

  it("keeps the count of messages after the marks, however many there are", async () => {
    const { wrapper, socket } = await open();
    await say(socket, 1, { [KEY]: "false", "beacon/interval_min": "0" });
    const header = wrapper.find(".appheader").element;
    expect(header.lastElementChild?.classList.contains("headmail")).toBe(true);
    expect(header.lastElementChild?.previousElementSibling?.classList.contains("headpills")).toBe(true);
  });
});

describe("a text that says RX only", () => {
  it("is a link in the Digipeater and Beacon rows, which opens Settings → Radio and flashes the RX only tickbox", async () => {
    const { wrapper, socket } = await open();
    await say(socket, 1, {
      [KEY]: "false",
      "radio/1/digipeat": "true",
      "beacon/interval_min": "30",
      "status/source": "text",
    });
    await tabButton(wrapper, "Settings")?.trigger("click");
    const digi = wrapper.findAll("#pane-settings fieldset").find((f) => f.find("legend").text() === "Digipeater");
    const line = digi?.find(".tncstatus button.linkbutton");
    expect(line?.text()).toBe("RX only: nothing is repeated");
    expect(line?.attributes("title")).toBe("Nothing is sent. Settings → Radio → RX only");
    await tabButton(wrapper, "My station")?.trigger("click");
    const rows = wrapper.findAll("#pane-beacon .statusfold .tncstatus button.linkbutton");
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every((r) => r.text() === "RX only: nothing is sent")).toBe(true);
    await rows[0]?.trigger("click");
    expect(wrapper.find("[aria-selected='true']").text()).toContain("Settings");
    await vi.waitFor(() => expect(flashed("set-station-transmit")).toBe(true));
    expect(
      document.getElementById("set-station-transmit")?.closest("fieldset")?.querySelector("legend")?.textContent,
    ).toContain("Radio");
  });

  it("is plain words in the rows while transmitting is on", async () => {
    const { wrapper, socket } = await open();
    await say(socket, 1, { "digi/enabled": "true" });
    await tabButton(wrapper, "Settings")?.trigger("click");
    expect(wrapper.findAll("#pane-settings .statusfold .linkbutton")).toEqual([]);
  });

  it("is a link in the toast of the daemon's refusal, which leads to the same place, and not in another refusal", async () => {
    const { wrapper, socket } = await open();
    socket.say({
      type: "error",
      cmd: "",
      key: null,
      text: "beacon_now: receive only: transmitting is switched off",
      code: "transmit.off",
      params: {},
    });
    await flushPromises();
    const toast = wrapper.find(".toast");
    expect(toast.find("button.linkbutton").text()).toBe("RX only: nothing is sent");
    await tabButton(wrapper, "Stations")?.trigger("click");
    await toast.find("button.linkbutton").trigger("click");
    expect(wrapper.find("[aria-selected='true']").text()).toContain("Settings");
    await vi.waitFor(() => expect(flashed("set-station-transmit")).toBe(true));
    socket.say({
      type: "error",
      cmd: "",
      key: null,
      text: "beacon_now: nothing was sent: the beacon is off",
      code: "beacon.not_sent",
      params: { reason: "the beacon is off" },
    });
    await flushPromises();
    expect(wrapper.find(".toast button.linkbutton").exists()).toBe(false);
    expect(wrapper.find(".toast").text()).toContain("nothing was sent");
  });
});

describe("a station with no radio, on a phone that opens the page by the code", () => {
  it("has the NeoAPRS mark alone, waiting for no radio, and Settings → Web page still shows the code", async () => {
    window.innerWidth = 390;
    window.innerHeight = 800;
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "radios", rev: 1, value: {} });
    const config = configValues({ "web/network": "true", "web/key": "k7m2-x9pq-4hrt" });
    config.urls = ["http://192.168.1.20:7303/"];
    socket.say({ type: "state", topic: "config", rev: 1, value: config });
    await flushPromises();
    expect(wrapper.findAll(".appheader .headpills .tag").map((m) => m.text())).toEqual(["NeoAPRS"]);
    expect(wrapper.find(".appheader").text()).not.toContain("waiting");
    await tabButton(wrapper, "Settings")?.trigger("click");
    await flushPromises();
    expect(wrapper.find("svg.phonecode").exists()).toBe(true);
  });
});
