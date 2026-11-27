import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { FakeMap, FakeMarker } from "@/test/fakemap";
import { FakeSocket } from "@/test/fakesocket";
import { configValues, errorOf, hello, mapFile, mapState, radioRow, status } from "@/test/fixtures";
import type { RadioRow } from "@/protocol/protocol";
import { mountApp, open, switchFace, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

describe("App: the first-run guide", () => {
  it("says no call set while the call is empty, the guide opens by itself, and the header's button opens it again", async () => {
    const { wrapper, socket } = await open();
    expect(wrapper.find(".appheader .nocall").exists()).toBe(false);
    expect(wrapper.find(".setup").exists()).toBe(false);
    socket.say({
      type: "state",
      topic: "config",
      rev: 1,
      value: configValues({ "beacon/interval_min": "0", "station/call": "", "station/lat": "", "station/lon": "" }),
    });
    socket.say(status({ call: "", lat: null, lon: null }));
    await flushPromises();
    const button = wrapper.find(".appheader .nocall");
    expect(button.text()).toBe("no call set");
    expect(wrapper.find(".appheader .call").exists()).toBe(false);
    expect(wrapper.find(".setup").exists()).toBe(true);
    expect(wrapper.find("#setup-call").exists()).toBe(true);
    await wrapper.find(".setup-close").trigger("click");
    expect(wrapper.find(".setup").exists()).toBe(false);
    await button.trigger("click");
    expect(wrapper.find(".setup").exists()).toBe(true);
    expect(tabButton(wrapper, "Messages")?.attributes("aria-selected")).toBe("true"); // the tab is where it was
  });

  it("opens the guide once: not again when the settings are told again, nor when the call is set", async () => {
    const { wrapper, socket } = await open();
    expect(wrapper.find(".setup").exists()).toBe(false);
    const empty = (rev: number) =>
      socket.say({
        type: "state",
        topic: "config",
        rev,
        value: configValues({ "beacon/interval_min": "0", "station/call": "" }),
      });
    empty(1);
    await flushPromises();
    expect(wrapper.find(".setup").exists()).toBe(true);
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await flushPromises();
    expect(wrapper.find(".setup").exists()).toBe(false);
    empty(2);
    await flushPromises();
    expect(wrapper.find(".setup").exists()).toBe(false);
    socket.say({ type: "state", topic: "config", rev: 3, value: configValues() });
    await flushPromises();
    expect(wrapper.find(".setup").exists()).toBe(false);
  });

  it("does not open the guide before the daemon has told its settings", async () => {
    const wrapper = mountApp();
    await flushPromises();
    FakeSocket.last().say(hello());
    await flushPromises();
    expect(wrapper.find(".setup").exists()).toBe(false);
  });

  it("opens the guide again from the link at the top of the Settings tab, with the answers the daemon has", async () => {
    const { wrapper } = await open();
    expect(wrapper.find(".setup").exists()).toBe(false);
    await tabButton(wrapper, "Settings")?.trigger("click");
    const setup = wrapper.find("#pane-settings button.setup-open");
    await setup.trigger("click");
    expect(wrapper.find(".setup").exists()).toBe(true);
    expect(wrapper.find<HTMLInputElement>("#setup-call").element.value).toBe("OH2GBA");
  });

  /** A fresh install: no call, no position, radio 1 alone, and the guide open on the first step. */
  async function fresh() {
    const { wrapper, socket } = await open();
    socket.say({
      type: "state",
      topic: "config",
      rev: 1,
      value: configValues({
        "beacon/interval_min": "0",
        "station/call": "",
        "station/lat": "",
        "station/lon": "",
        "serial/baud": "",
      }),
    });
    socket.say(status({ call: "", lat: null, lon: null }));
    socket.say({ type: "state", topic: "map", rev: 0, value: mapState({ blocked: "no_position", box: null }) });
    socket.say({ type: "state", topic: "radios", rev: 0, value: { "1": radioRow(1, "kenwood-tnc2") } });
    await flushPromises();
    return { wrapper, socket };
  }

  it("takes the position from a click on the map on the position step, and shows the marker", async () => {
    const { wrapper } = await fresh();
    await wrapper.find("#setup-call").setValue("oh2abc");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.find(".setup-step-name").text()).toBe("Position");
    const pins = () => FakeMarker.live().filter((m) => m.element.classList.contains("setuppin"));
    expect(pins()).toHaveLength(0);
    FakeMap.last().fire("click", { lngLat: { lat: 60.1699, lng: 24.9402 } });
    await flushPromises();
    expect(wrapper.find<HTMLInputElement>("#setup-lat").element.value).toBe("60.1699");
    expect(wrapper.find<HTMLInputElement>("#setup-lon").element.value).toBe("24.9402");
    expect(wrapper.find<HTMLInputElement>("#setup-locator").element.value).toBe("KP20le");
    expect(pins()).toHaveLength(1);
    expect(pins()[0]?.lngLat).toEqual([24.9402, 60.1699]);
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeUndefined();
  });

  it("ignores a click on the map on the other steps, and takes the marker away with the guide", async () => {
    const { wrapper } = await fresh();
    FakeMap.last().fire("click", { lngLat: { lat: 60.1, lng: 24.9 } });
    await flushPromises();
    expect(wrapper.find("#setup-call").exists()).toBe(true);
    await wrapper.find("#setup-call").setValue("oh2abc");
    await wrapper.find("form").trigger("submit");
    FakeMap.last().fire("click", { lngLat: { lat: 60.1, lng: 24.9 } });
    await flushPromises();
    await wrapper.find(".setup-close").trigger("click");
    await flushPromises();
    expect(FakeMarker.live().filter((m) => m.element.classList.contains("setuppin"))).toHaveLength(0);
    await wrapper.find(".appheader .nocall").trigger("click");
    expect(FakeMarker.live().filter((m) => m.element.classList.contains("setuppin"))).toHaveLength(1);
  });

  it("goes through the four steps, saves the radio as it is changed (the Radio step is live) and at Finish one set_config with the other keys that changed, then closes when the daemon tells the settings", async () => {
    const { wrapper, socket } = await fresh();
    const configs = () => socket.sent.filter((c) => (c as { cmd: string }).cmd === "set_config");
    const next = () => wrapper.find("form").trigger("submit");
    await wrapper.find("#setup-call").setValue("oh2abc-9");
    await next();
    FakeMap.last().fire("click", { lngLat: { lat: 60.17, lng: 24.94 } });
    await flushPromises();
    expect(configs()).toEqual([]);
    await next();
    // The place goes on its own as Next leaves the Position step, so that the daemon can make the
    // map round it.
    expect(configs()).toEqual([{ cmd: "set_config", values: { "station/lat": "60.17", "station/lon": "24.94" } }]);
    socket.say({
      type: "state",
      topic: "config",
      rev: 2,
      value: configValues(
        { "beacon/interval_min": "0", "station/call": "", "station/lat": "60.17", "station/lon": "24.94" },
        { "radio/1/baud": "" },
      ),
    });
    await flushPromises();
    await wrapper.findAll(".setup-symbol")[1]?.trigger("click"); // the car
    await next();
    expect(wrapper.find(".setup-step-name").text()).toBe("Radio");
    // When the socket opened, and when the guide came to its radio.
    expect(socket.sent.filter((c) => (c as { cmd: string }).cmd === "list_ports")).toHaveLength(2);
    socket.say({
      type: "ports",
      sound_cards: [],
      keying: "",
      search: true,
      find: true,
      ports: [{ device: "/dev/ttyUSB0", description: "FT232R USB UART", hwid: "n/a", vid: null, pid: null }],
      radio: null,
    });
    await flushPromises();
    await wrapper.find("#setup-radio-1-port").setValue("/dev/ttyUSB0");
    expect(configs()).toHaveLength(2);
    // At once, as from the Settings tab.
    expect(configs()[1]).toEqual({ cmd: "set_config", values: { "radio/1/port": "/dev/ttyUSB0" } });
    // The daemon tells the settings with the port, and answers that save.
    socket.say({
      type: "state",
      topic: "config",
      rev: 3,
      value: configValues(
        { "beacon/interval_min": "0", "station/call": "", "station/lat": "60.17", "station/lon": "24.94" },
        { "radio/1/port": "/dev/ttyUSB0" },
      ),
    });
    await flushPromises();
    await next();
    expect(configs()[2]).toEqual({
      cmd: "set_config",
      values: {
        "station/call": "OH2ABC-9",
        "station/symbol_code": ">",
        "beacon/interval_min": "30",
      },
    });
    expect(wrapper.find(".setup").exists()).toBe(true);
    socket.say({
      type: "state",
      topic: "config",
      rev: 4,
      value: configValues(
        { "station/call": "OH2ABC-9", "station/lat": "60.17", "station/lon": "24.94", "station/symbol_code": ">" },
        { "radio/1/port": "/dev/ttyUSB0" },
      ),
    });
    await flushPromises();
    expect(wrapper.find(".setup").exists()).toBe(false);
    expect(configs()).toHaveLength(3);
    // Our call is in the settings and the status, not in the header.
    expect(wrapper.find(".appheader").text()).not.toContain("OH2ABC");
    expect(wrapper.find(".appheader .nocall").exists()).toBe(false);
  });

  it("shows the daemon's refusal under the field it names and keeps the guide open", async () => {
    const { wrapper, socket } = await fresh();
    await wrapper.find("#setup-call").setValue("oh2abc");
    await wrapper.find("form").trigger("submit");
    await wrapper.find("#setup-lat").setValue("60.17");
    await wrapper.find("#setup-lon").setValue("24.94");
    for (let i = 0; i < 4; i++) await wrapper.find("form").trigger("submit");
    socket.say(
      errorOf("set_config: station/call: call 'OH2ABC' has an SSID above 15", "call.ssid", {
        value: "OH2ABC",
        max: 15,
      }),
    );
    await flushPromises();
    expect(wrapper.find(".setup-step-name").text()).toBe("Call");
    expect(wrapper.find(".setup .field-error").text()).toBe("call 'OH2ABC' has an SSID above 15");
  });

  it("sends the place as the Position step is left, so that the daemon begins the map, and the header shows the download's percent", async () => {
    const { wrapper, socket } = await fresh();
    await wrapper.find("#setup-call").setValue("oh2abc");
    await wrapper.find("form").trigger("submit");
    await wrapper.find("#setup-lat").setValue("60.17");
    await wrapper.find("#setup-lon").setValue("24.94");
    for (let i = 0; i < 2; i++) await wrapper.find("form").trigger("submit");
    const commands = () => socket.sent.map((c) => (c as { cmd: string }).cmd);
    // The place, sent as the Position step was left; the daemon makes the map round a new place by
    // itself.
    expect(commands().filter((c) => c === "set_config")).toHaveLength(1);
    expect(commands()).not.toContain("map_wanted");
    expect(commands()).not.toContain("map_estimate");
    expect(wrapper.find(".setup .mapfetch-button").exists()).toBe(false);
    expect(wrapper.find(".setup #setup-radius").exists()).toBe(false);
    socket.say({
      type: "state",
      topic: "map",
      rev: 0,
      value: mapState({ state: "downloading", step: "area", percent: 42, downloaded: 1_000_000, radius_km: 150 }),
    });
    await flushPromises();
    expect(wrapper.find(".setup .setup-mapline").text()).toBe("Downloading the map of your area…");
    expect(wrapper.find(".setup .mapfetch-progress").exists()).toBe(false);
    expect(wrapper.find(".appheader .pill-map").text()).toBe("Map 42 %");
    socket.say({ type: "state", topic: "map", rev: 1, value: mapState({ state: "ready", detail: mapFile() }) });
    await flushPromises();
    expect(wrapper.find(".appheader .pill-map").exists()).toBe(false);
    expect(wrapper.find(".setup .setup-mapline").exists()).toBe(false);
  });

  /**
   * A station with no radio on the Radio step: the guide's call and place given, the topic `radios`
   * empty; `type` is added from its one box, with the daemon's answer and row.
   */
  async function firstRadio(type: string, row: Partial<RadioRow>, values: Record<string, string>) {
    const { wrapper, socket } = await fresh();
    socket.say({ type: "state", topic: "radios", rev: 1, value: {} });
    await wrapper.find("#setup-call").setValue("oh2abc");
    await wrapper.find("form").trigger("submit");
    await wrapper.find("#setup-lat").setValue("60.17");
    await wrapper.find("#setup-lon").setValue("24.94");
    for (let i = 0; i < 2; i++) await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(wrapper.find(".setup-step-name").text()).toBe("Radio");
    await wrapper.find("#setup-radio-add").setValue(type);
    await wrapper.find("#setup-radio-add-button").trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "radio_add", type });
    socket.say({ type: "radio_added", id: 3 });
    socket.say({
      type: "state",
      topic: "config",
      rev: 2,
      value: configValues({ "station/call": "", "station/lat": "60.17", "station/lon": "24.94" }, values),
    });
    socket.say({ type: "state", topic: "radios", rev: 2, value: { "3": radioRow(3, type, row) } });
    await flushPromises();
    const box = wrapper.find(".setup .setup-body fieldset.subbox");
    const commands = () => socket.sent.map((c) => (c as { cmd: string }).cmd);
    return { wrapper, socket, box, commands };
  }

  it("adds a LoRa board on the network as a station's first radio: its box asks for the board's host and port alone, says Not connected with nothing of an address, and the page shows no error", async () => {
    const { wrapper, socket, box } = await firstRadio(
      "lora-tcp",
      { state: "waiting", problem: { code: "radio.not_connected", params: { name: "LoRa" } } },
      { "radio/3/tcp_host": "", "radio/3/tcp_port": "8001", "radio/3/beacon": "true", "radio/3/path": "" },
    );
    expect(box.find("legend").text()).toBe("LoRa radio");
    expect(box.find<HTMLSelectElement>("#setup-radio-3-type").element.value).toBe("lora-tcp");
    expect([
      box.find<HTMLInputElement>("#setup-radio-3-tcp_host").element.value,
      box.find<HTMLInputElement>("#setup-radio-3-tcp_port").element.value,
    ]).toEqual(["", "8001"]);
    expect(["port", "baud", "find"].filter((part) => box.find(`#setup-radio-3-${part}`).exists())).toEqual([]);
    expect(box.find(".radiostatus .tncstatus").text()).toContain("Not connected");
    expect(box.text()).not.toMatch(/127\.0\.0\.1|8001 |socket|tcp:/);
    expect(wrapper.find(".toast").exists()).toBe(false);
    // A board that sends: the station is no RX only one.
    expect(switchFace(wrapper)).toBe("RX + TX");
    // The Radio step has no RX only; on a desktop the header and its switch stay while the guide is open.
    expect(wrapper.findAll(".setup .field label").map((label) => label.text())).not.toContain("RX only");
    expect(wrapper.find("#set-station-transmit").exists()).toBe(false);
    expect(wrapper.find(".app").classes()).toContain("guide-open");
    expect(wrapper.find(".appheader #rx-switch").exists()).toBe(true);
    await wrapper.find(".setup #setup-radio-3-tcp_host").setValue("192.168.1.20");
    await wrapper.find(".setup #setup-radio-3-tcp_host").trigger("keydown", { key: "Enter" });
    expect(socket.sent.filter((c) => (c as { cmd: string }).cmd === "set_config").at(-1)).toEqual({
      cmd: "set_config",
      values: { "radio/3/tcp_host": "192.168.1.20" },
    });
  });

  it("adds a text monitor as a station's first radio: the header says the station only receives, its box offers its port and speed alone, and nothing on the page would send", async () => {
    const { wrapper, box, commands } = await firstRadio(
      "tnc-text",
      {},
      { "radio/3/port": "/dev/ttyUSB0", "radio/3/baud": "9600" },
    );
    expect([switchFace(wrapper), wrapper.find("#rx-switch").attributes("title")]).toEqual([
      "RX only",
      "Nothing is sent. Settings → Radio",
    ]);
    expect(box.find("legend").text()).toBe("Packet radio");
    expect(["port", "baud"].map((part) => box.find(`#setup-radio-3-${part}`).exists())).toEqual([true, true]);
    expect(
      ["find", "path", "digipeat", "tcp_host"].filter(
        (part) => wrapper.find(`#setup-radio-3-${part}`).exists() || wrapper.find(`#set-radio-3-${part}`).exists(),
      ),
    ).toEqual([]);
    expect(wrapper.find(".toast").exists()).toBe(false);
    await wrapper.find(".setup-close").trigger("click");
    const beaconNow = wrapper
      .findAll<HTMLButtonElement>("#pane-beacon button")
      .find((button) => button.text() === "Beacon now");
    // My station's Beacon now: greyed, or not there.
    expect(beaconNow === undefined || beaconNow.element.disabled).toBe(true);
    expect(
      commands().filter((cmd) => ["beacon_now", "status_now", "send_message", "find_radio"].includes(cmd)),
    ).toEqual([]);
  });

  it("has the Radio step's boxes beside the Settings tab's with no id twice on the page, and its radio stays when the guide is closed", async () => {
    const { wrapper, socket } = await fresh();
    await wrapper.find("#setup-call").setValue("oh2abc");
    await wrapper.find("form").trigger("submit");
    await wrapper.find("#setup-lat").setValue("60.17");
    await wrapper.find("#setup-lon").setValue("24.94");
    for (let i = 0; i < 2; i++) await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(wrapper.find(".setup-step-name").text()).toBe("Radio");
    expect(wrapper.find("#pane-settings #set-radio-1-enabled").exists()).toBe(true);
    expect(wrapper.find(".setup #setup-radio-1-enabled").exists()).toBe(true);
    const ids = [...document.querySelectorAll("[id]")].map((e) => e.id);
    expect(ids.filter((id, i) => ids.indexOf(id) !== i)).toEqual([]);
    await wrapper.find(".setup #setup-radio-1-baud").setValue("4800");
    await wrapper.find(".setup #setup-radio-1-baud").trigger("keydown", { key: "Enter" });
    const configs = socket.sent.filter((c) => (c as { cmd: string }).cmd === "set_config");
    expect(configs.at(-1)).toEqual({ cmd: "set_config", values: { "radio/1/baud": "4800" } });
    await wrapper.find(".setup-close").trigger("click");
    // The same settings: nothing waits for Finish.
    expect(wrapper.find<HTMLInputElement>("#pane-settings #set-radio-1-baud").element.value).toBe("4800");
  });
});
