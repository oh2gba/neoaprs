import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { FakeMap, FakeMarker } from "@/test/fakemap";
import { FakeSocket } from "@/test/fakesocket";
import { configValues, errorOf, hello, mapState, status } from "@/test/fixtures";
import { mountApp, open, tabButton, useAppHarness } from "@/test/app";

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
    const empty = (rev: number) => socket.say({ type: "state", topic: "config", rev, value: configValues({ "beacon/interval_min": "0", "station/call": "" }) });
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

  /** A fresh install: no call, no position, and the guide open on the first step. */
  async function fresh() {
    const { wrapper, socket } = await open();
    socket.say({
      type: "state",
      topic: "config",
      rev: 1,
      value: configValues({ "beacon/interval_min": "0", "station/call": "", "station/lat": "", "station/lon": "", "serial/baud": "" }),
    });
    socket.say(status({ call: "", lat: null, lon: null }));
    socket.say({ type: "state", topic: "map", rev: 0, value: mapState({ blocked: "no position", box: null }) });
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

  it("goes through the five steps and sends one set_config with the keys that changed, then closes when the daemon tells the settings", async () => {
    const { wrapper, socket } = await fresh();
    const configs = () => socket.sent.filter((c) => (c as { cmd: string }).cmd === "set_config");
    const next = () => wrapper.find("form").trigger("submit");
    await wrapper.find("#setup-call").setValue("oh2abc-9");
    await next();
    FakeMap.last().fire("click", { lngLat: { lat: 60.17, lng: 24.94 } });
    await flushPromises();
    expect(configs()).toEqual([]);
    await next();
    // the place goes on its own as Next leaves the Position step, so that the daemon can make the map round it
    expect(configs()).toEqual([{ cmd: "set_config", values: { "station/lat": "60.17", "station/lon": "24.94" } }]);
    socket.say({
      type: "state",
      topic: "config",
      rev: 2,
      value: configValues({ "beacon/interval_min": "0", "station/call": "", "station/lat": "60.17", "station/lon": "24.94", "serial/baud": "" }),
    });
    await flushPromises();
    await wrapper.findAll(".setup-symbol")[1]?.trigger("click"); // the car
    await next();
    expect(wrapper.find(".setup-step-name").text()).toBe("Radio");
    expect(socket.sent.filter((c) => (c as { cmd: string }).cmd === "list_ports")).toHaveLength(2); // when the socket opened, and when the guide came to its radio
    socket.say({ type: "ports", search: true, ports: [{ device: "/dev/ttyUSB0", description: "FT232R USB UART", hwid: "n/a", vid: null, pid: null }] });
    await flushPromises();
    await wrapper.find("#setup-port").setValue("/dev/ttyUSB0");
    await next();
    expect(wrapper.find(".setup-step-name").text()).toBe("Map");
    await wrapper.find("#setup-radius").setValue("200");
    expect(configs()).toHaveLength(1);
    await next();
    expect(configs()[1]).toEqual({
      cmd: "set_config",
      values: {
        "station/call": "OH2ABC-9",
        "station/symbol_code": ">",
        "serial/port": "/dev/ttyUSB0",
        "map/radius_km": "200",
        "beacon/interval_min": "30",
      },
    });
    expect(wrapper.find(".setup").exists()).toBe(true);
    socket.say({
      type: "state",
      topic: "config",
      rev: 3,
      value: configValues({
        "station/call": "OH2ABC-9",
        "station/lat": "60.17",
        "station/lon": "24.94",
        "station/symbol_code": ">",
        "serial/port": "/dev/ttyUSB0",
        "map/radius_km": "200",
      }),
    });
    await flushPromises();
    expect(wrapper.find(".setup").exists()).toBe(false);
    expect(configs()).toHaveLength(2);
    expect(wrapper.find(".appheader").text()).not.toContain("OH2ABC"); // (our call is in the settings and the status, not in the header)
    expect(wrapper.find(".appheader .nocall").exists()).toBe(false);
  });

  it("shows the daemon's refusal under the field it names and keeps the guide open", async () => {
    const { wrapper, socket } = await fresh();
    await wrapper.find("#setup-call").setValue("oh2abc");
    await wrapper.find("form").trigger("submit");
    await wrapper.find("#setup-lat").setValue("60.17");
    await wrapper.find("#setup-lon").setValue("24.94");
    for (let i = 0; i < 4; i++) await wrapper.find("form").trigger("submit");
    socket.say(errorOf("set_config: station/call: 'OH2ABC' is already in use"));
    await flushPromises();
    expect(wrapper.find(".setup-step-name").text()).toBe("Call");
    expect(wrapper.find(".setup .field-error").text()).toBe("'OH2ABC' is already in use");
  });

  it("makes the map from the guide: the settings go first, the command when the daemon has told them", async () => {
    const { wrapper, socket } = await fresh();
    await wrapper.find("#setup-call").setValue("oh2abc");
    await wrapper.find("form").trigger("submit");
    await wrapper.find("#setup-lat").setValue("60.17");
    await wrapper.find("#setup-lon").setValue("24.94");
    for (let i = 0; i < 3; i++) await wrapper.find("form").trigger("submit");
    const commands = () => socket.sent.map((c) => (c as { cmd: string }).cmd);
    expect(commands().filter((c) => c === "set_config")).toHaveLength(1); // (the place, sent as the Position step was left)
    await wrapper.find(".setup .mapfetch-button").trigger("click");
    expect(commands().filter((c) => c === "set_config")).toHaveLength(2);
    expect(commands()).not.toContain("map_estimate");
    socket.say({
      type: "state",
      topic: "config",
      rev: 2,
      value: configValues({ "station/call": "OH2ABC", "station/lat": "60.17", "station/lon": "24.94" }),
    });
    await flushPromises();
    expect(commands().at(-1)).toBe("map_estimate");
    socket.say({
      type: "state",
      topic: "map",
      rev: 0,
      value: mapState({ estimate: { bytes: 493_000_000, tiles: 41233, radius_km: 150, maxzoom: 12, box: [22.1, 58.8, 27.8, 61.5], build: "20261022" } }),
    });
    await flushPromises();
    await wrapper.find(".setup .mapfetch-button").trigger("click");
    expect(commands().at(-1)).toBe("map_fetch");
  });
});
