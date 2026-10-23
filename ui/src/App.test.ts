import "@/test/mockmap";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App.vue";
import { PROTOCOL } from "@/protocol/lists";
import { FakeMap, FakeMarker, fakeState, resetFakes } from "@/test/fakemap";
import { FakeSocket } from "@/test/fakesocket";
import { ago, bulletin, configValues, incoming, mapFile, mapState, message, packet, station, status, tncState } from "@/test/fixtures";

const stations = {
  OH2GBA: station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94, symbol_table: "", symbol_code: "", distance_km: null, bearing_deg: null }),
  "OH2PU-9": station("OH2PU-9", { lat: 60.2, lon: 24.65, distance_km: 16, bearing_deg: 282, last_heard: ago(30) }),
  OH2RDG: station("OH2RDG", { symbol_table: "N", symbol_code: "#", lat: 60.12, lon: 24.49, last_heard: ago(10) }),
  OH2NOPOS: station("OH2NOPOS", { lat: null, lon: null, last_heard: ago(90) }),
};

const messages = {
  "1": message(1, { to_call: "OH2RDG", text: "Hello Pekka", state: "acked", attempts: 1, at: ago(500) }),
  "2": incoming(2, "OH2RDG", { text: "Moi!", at: ago(400) }),
  "3": incoming(3, "OH2PU-9", { text: "Are you there?", at: ago(300) }),
};

async function open() {
  const wrapper = mount(App, { attachTo: document.body });
  await flushPromises();
  const socket = FakeSocket.last();
  socket.say({ type: "hello", protocol: PROTOCOL, version: "0.1.0", topics: [] });
  socket.say({ type: "state", topic: "stations", rev: 0, value: stations });
  socket.say({ type: "state", topic: "packets", rev: 0, value: { "1": packet(1), "2": packet(2, { summary: "second" }) } });
  socket.say({ type: "state", topic: "tnc", rev: 0, value: tncState() });
  socket.say({ type: "state", topic: "config", rev: 0, value: configValues({ "map/hide_after_min": "0" }) }); // the fixtures' times are fixed, so nothing times out
  socket.say({ type: "state", topic: "messages", rev: 0, value: messages });
  socket.say({ type: "state", topic: "station_prefs", rev: 0, value: { OH2RDG: { path: "OH2RCH-2", hide_after_min: null, attempts: null, rf_only: false } } });
  socket.say(status());
  await flushPromises();
  return { wrapper, socket };
}

const tabButton = (wrapper: VueWrapper, title: string) => wrapper.findAll("[role='tab']").find((t) => t.text().startsWith(title));

beforeEach(() => {
  FakeSocket.all = [];
  resetFakes();
  localStorage.clear();
  sessionStorage.clear();
  vi.stubGlobal("WebSocket", FakeSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(document, "visibilityState");
  document.body.replaceChildren();
});

describe("App", () => {
  it("says connecting, then radio ok with our call in the header", async () => {
    const wrapper = mount(App, { attachTo: document.body });
    await flushPromises();
    expect(wrapper.find(".appheader").text()).toContain("connecting");
    const socket = FakeSocket.last();
    socket.say({ type: "hello", protocol: PROTOCOL, version: "0.1.0", topics: [] });
    socket.say({ type: "state", topic: "tnc", rev: 0, value: tncState() });
    socket.say({ type: "state", topic: "config", rev: 0, value: configValues() });
    await flushPromises();
    const header = wrapper.find(".appheader").text();
    expect(header).toContain("NeoAPRS");
    expect(header).toContain("OH2GBA");
    expect(header).toContain("radio ok");
    expect(header).not.toContain("brainbox");
  });

  it("says daemon offline when the socket closes, and connects again", async () => {
    const { wrapper, socket } = await open();
    vi.useFakeTimers();
    socket.hangUp();
    await flushPromises();
    expect(wrapper.find(".appheader .link-bad").text()).toBe("daemon offline");
    vi.advanceTimersByTime(1000);
    vi.useRealTimers();
    expect(FakeSocket.all).toHaveLength(2);
  });

  it("says no call set while the call is empty, the guide opens by itself, and the header's button opens it again", async () => {
    const { wrapper, socket } = await open();
    expect(wrapper.find(".appheader .nocall").exists()).toBe(false);
    expect(wrapper.find(".setup").exists()).toBe(false);
    socket.say({
      type: "state",
      topic: "config",
      rev: 1,
      value: configValues({ "station/call": "", "station/lat": "", "station/lon": "", "map/hide_after_min": "0" }),
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
    expect(tabButton(wrapper, "Stations")?.attributes("aria-selected")).toBe("true"); // the tab is where it was
  });

  it("opens the guide once: not again when the settings are told again, nor when the call is set", async () => {
    const { wrapper, socket } = await open();
    expect(wrapper.find(".setup").exists()).toBe(false);
    const empty = (rev: number) => socket.say({ type: "state", topic: "config", rev, value: configValues({ "station/call": "" }) });
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
    const wrapper = mount(App, { attachTo: document.body });
    await flushPromises();
    FakeSocket.last().say({ type: "hello", protocol: PROTOCOL, version: "0.1.0", topics: [] });
    await flushPromises();
    expect(wrapper.find(".setup").exists()).toBe(false);
  });

  it("opens the guide again from the Setup button of the Settings tab, with the answers the daemon has", async () => {
    const { wrapper } = await open();
    expect(wrapper.find(".setup").exists()).toBe(false);
    await tabButton(wrapper, "Settings")?.trigger("click");
    const setup = wrapper.findAll("#pane-settings button").find((b) => b.text() === "Setup");
    await setup?.trigger("click");
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
      value: configValues({ "station/call": "", "station/lat": "", "station/lon": "", "serial/baud": "", "map/hide_after_min": "0" }),
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
    expect(wrapper.find("h3").text()).toBe("Position");
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
    await next();
    await wrapper.findAll(".setup-symbol")[1]?.trigger("click"); // the car
    await next();
    expect(wrapper.find("h3").text()).toBe("Radio");
    expect(socket.sent.filter((c) => (c as { cmd: string }).cmd === "list_ports")).toHaveLength(1);
    socket.say({ type: "ports", search: true, ports: [{ device: "/dev/ttyUSB0", description: "FT232R USB UART", hwid: "n/a", vid: null, pid: null }] });
    await flushPromises();
    await wrapper.find("#setup-port").setValue("/dev/ttyUSB0");
    await next();
    expect(wrapper.find("h3").text()).toBe("Map");
    await wrapper.find("#setup-radius").setValue("200");
    expect(configs()).toEqual([]);
    await next();
    expect(configs()).toEqual([
      {
        cmd: "set_config",
        values: {
          "station/call": "OH2ABC-9",
          "station/lat": "60.17",
          "station/lon": "24.94",
          "station/symbol_code": ">",
          "serial/port": "/dev/ttyUSB0",
          "map/radius_km": "200",
        },
      },
    ]);
    expect(wrapper.find(".setup").exists()).toBe(true);
    socket.say({
      type: "state",
      topic: "config",
      rev: 2,
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
    expect(configs()).toHaveLength(1);
    expect(wrapper.find(".appheader .call").text()).toBe("OH2ABC-9"); // (the header follows the settings, the status comes every 10 s)
    expect(wrapper.find(".appheader .nocall").exists()).toBe(false);
  });

  it("shows the daemon's refusal under the field it names and keeps the guide open", async () => {
    const { wrapper, socket } = await fresh();
    await wrapper.find("#setup-call").setValue("oh2abc");
    await wrapper.find("form").trigger("submit");
    await wrapper.find("#setup-lat").setValue("60.17");
    await wrapper.find("#setup-lon").setValue("24.94");
    for (let i = 0; i < 4; i++) await wrapper.find("form").trigger("submit");
    socket.say({ type: "error", text: "set_config: station/call: 'OH2ABC' is already in use" });
    await flushPromises();
    expect(wrapper.find("h3").text()).toBe("Call");
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
    await wrapper
      .findAll(".setup .mapfetch button")
      .find((b) => b.text() === "Download")
      ?.trigger("click");
    expect(commands().filter((c) => c === "set_config")).toHaveLength(1);
    expect(commands()).not.toContain("map_fetch");
    socket.say({
      type: "state",
      topic: "config",
      rev: 2,
      value: configValues({ "station/call": "OH2ABC", "station/lat": "60.17", "station/lon": "24.94", "map/hide_after_min": "0" }),
    });
    await flushPromises();
    expect(commands().at(-1)).toBe("map_fetch");
  });

  it("shows the four stations on the map and in the table", async () => {
    const { wrapper } = await open();
    expect(FakeMarker.live()).toHaveLength(3); // the fourth has no position
    expect(wrapper.findAll("#pane-stations tbody tr")).toHaveLength(4);
    expect(wrapper.find("#pane-stations tbody tr").text()).toContain("OH2GBA");
    expect(FakeMap.last().jumps).toEqual([{ center: [24.94, 60.17], zoom: 9 }]); // the map opened on the world before the daemon said where we are
  });

  it("keeps a timed out station off the map but in the table, and shows it while it is selected", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ "map/hide_after_min": "60" }) });
    const before = (seconds: number) => new Date(Date.now() - seconds * 1000).toISOString();
    socket.say({
      type: "patch",
      topic: "stations",
      rev: 1,
      ops: [
        { op: "set", key: "OH2RDG", value: { ...stations.OH2RDG, last_position_at: before(3 * 3600) } },
        { op: "set", key: "OH2PU-9", value: { ...stations["OH2PU-9"], last_position_at: before(60) } },
      ],
    });
    await flushPromises();
    const shown = () => FakeMarker.live().map((m) => m.element.textContent);
    expect(shown()).not.toContain("OH2RDG");
    expect(shown()).toContain("OH2PU-9");
    const row = () => wrapper.findAll("#pane-stations tbody tr").find((r) => r.text().includes("OH2RDG"));
    expect(row()?.text()).toContain("timed out");
    await row()?.trigger("click");
    await flushPromises();
    expect(FakeMap.last().flights).toHaveLength(1);
    expect(shown()).toContain("OH2RDG");
    expect(wrapper.find(".card").text()).toContain("timed out");
    await wrapper.find(".card button[aria-label='Close']").trigger("click");
    await flushPromises();
    expect(shown()).not.toContain("OH2RDG");
  });

  it("draws our own station with the symbol of the settings, the daemon having heard none", async () => {
    await open();
    const ours = FakeMarker.live().find((m) => m.element.textContent === "OH2GBA");
    expect(ours?.element.querySelectorAll(".stn-layer")).toHaveLength(1);
  });

  it("shows the packets as they arrive, newest first", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Packets")?.trigger("click");
    expect(wrapper.find("#pane-packets tbody tr").text()).toContain("second");
    socket.say({ type: "patch", topic: "packets", rev: 1, ops: [{ op: "set", key: "3", value: packet(3, { summary: "third" }) }] });
    await flushPromises();
    expect(wrapper.find("#pane-packets tbody tr").text()).toContain("third");
  });

  it("shows the radio link in the TNC tab and asks for a reconnect", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "TNC")?.trigger("click");
    expect(wrapper.find("#pane-tnc").text()).toContain("9600 baud");
    await wrapper.find("#pane-tnc button").trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "tnc_reconnect" });
  });

  it("sends a beacon from the Beacon tab after two clicks, and shows the times the status tells", async () => {
    const { wrapper, socket } = await open();
    socket.say(status({ beacon_interval_min: 15, beacon_last_sent: ago(60), beacon_next_due: new Date(Date.now() + 840_000).toISOString() }));
    await flushPromises();
    await tabButton(wrapper, "Beacon")?.trigger("click");
    expect(wrapper.find("#pane-beacon .beaconbox").text()).toContain("every 15 min");
    await wrapper.find("#pane-beacon .beaconbox button").trigger("click");
    expect(socket.sent).not.toContainEqual({ cmd: "beacon_now" });
    await wrapper.find("#pane-beacon .beaconbox button").trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "beacon_now" });
  });

  it("previews the beacon packet and saves the beacon's settings from the Beacon tab", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Beacon")?.trigger("click");
    expect(wrapper.find("#pane-beacon .beacon-preview code").text()).toBe("OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS");
    await wrapper.find("#pane-beacon #set-station-comment").setValue("hello");
    await wrapper.find("#pane-beacon #set-beacon-path").setValue("");
    expect(wrapper.find("#pane-beacon .beacon-preview code").text()).toBe("OH2GBA>APZNEO:=6010.20N/02456.40E-hello");
    await wrapper.find("#pane-beacon form").trigger("submit");
    expect(socket.sent).toContainEqual({ cmd: "set_config", values: { "station/comment": "hello", "beacon/path": "" } });
    expect(wrapper.find("#pane-settings #set-station-comment").exists()).toBe(false);
  });

  it("selects a station by a marker, shows its card, and forgets it", async () => {
    const { wrapper, socket } = await open();
    FakeMarker.live()
      .find((m) => m.element.textContent === "OH2PU-9")
      ?.element.click();
    await flushPromises();
    expect(wrapper.find(".card").text()).toContain("OH2PU-9");
    expect(wrapper.find("#pane-stations tr.selected").text()).toContain("OH2PU-9");
    await wrapper.find(".card-foot .forget").trigger("click");
    await wrapper.find(".card-foot .forget").trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "forget_station", call: "OH2PU-9" });
    expect(wrapper.find(".card").exists()).toBe(false);
  });

  it("flies the map to a station picked in the table", async () => {
    const { wrapper } = await open();
    await wrapper
      .findAll("#pane-stations tbody tr")
      .find((r) => r.text().includes("OH2RDG"))
      ?.trigger("click");
    await flushPromises();
    expect(FakeMap.last().flights).toHaveLength(1);
    expect(wrapper.find(".card").text()).toContain("OH2RDG");
  });

  it("lets go of a station the daemon no longer has", async () => {
    const { wrapper, socket } = await open();
    await wrapper
      .findAll("#pane-stations tbody tr")
      .find((r) => r.text().includes("OH2RDG"))
      ?.trigger("click");
    socket.say({ type: "patch", topic: "stations", rev: 1, ops: [{ op: "del", key: "OH2RDG" }] });
    await flushPromises();
    expect(wrapper.find(".card").exists()).toBe(false);
  });

  it("sets and clears the timeout of a station from its card, takes it from the daemon, and keeps it out of the conversation", async () => {
    const { wrapper, socket } = await open();
    await wrapper
      .findAll("#pane-stations tbody tr")
      .find((r) => r.text().includes("OH2PU-9"))
      ?.trigger("click");
    const field = () => wrapper.find<HTMLInputElement>(".card .timeout-input");
    await field().setValue("45");
    expect(socket.sent).toContainEqual({ cmd: "set_station_timeout", call: "OH2PU-9", minutes: 45 });
    socket.say({
      type: "patch",
      topic: "station_prefs",
      rev: 1,
      ops: [{ op: "set", key: "OH2PU-9", value: { path: null, hide_after_min: 45, attempts: null, rf_only: false } }],
    });
    await flushPromises();
    expect(field().element.value).toBe("45");
    await wrapper.find(".card .timeoutbox .use-default").trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "clear_station_timeout", call: "OH2PU-9" });
    await tabButton(wrapper, "Messages")?.trigger("click");
    await wrapper.find("#pane-messages .conv").trigger("click");
    expect(wrapper.find("#pane-messages .timeout-input").exists()).toBe(false); // the map timeout is the station's, not the conversation's
  });

  it("ticks RF only from the card and from the conversation header, sends it, and follows the daemon", async () => {
    const { wrapper, socket } = await open();
    await wrapper
      .findAll("#pane-stations tbody tr")
      .find((r) => r.text().includes("OH2PU-9"))
      ?.trigger("click");
    await wrapper.find(".card .rfonly input").setValue(true);
    expect(socket.sent).toContainEqual({ cmd: "set_station_rf_only", call: "OH2PU-9", on: true });
    socket.say({
      type: "patch",
      topic: "station_prefs",
      rev: 1,
      ops: [{ op: "set", key: "OH2PU-9", value: { path: null, hide_after_min: null, attempts: null, rf_only: true } }],
    });
    await flushPromises();
    expect(wrapper.find<HTMLInputElement>(".card .rfonly input").element.checked).toBe(true);
    await tabButton(wrapper, "Messages")?.trigger("click");
    await wrapper
      .findAll("#pane-messages .conv")
      .find((c) => c.text().includes("OH2PU-9"))
      ?.trigger("click");
    const header = wrapper.find<HTMLInputElement>("#pane-messages .thread-head .rfonly input");
    expect(header.element.checked).toBe(true);
    await header.setValue(false);
    expect(socket.sent).toContainEqual({ cmd: "set_station_rf_only", call: "OH2PU-9", on: false });
  });

  it("has the map's default timeout on the Settings tab and the station and beacon keys on the Beacon tab, none twice", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ "map/hide_after_min": "1440" }) });
    await flushPromises();
    expect(wrapper.find("#pane-settings #set-map-hide_after_min").exists()).toBe(true);
    expect(wrapper.find("#pane-settings #set-station-call").exists()).toBe(false);
    expect(wrapper.find("#pane-beacon #set-station-call").exists()).toBe(true);
    expect(wrapper.find("#pane-beacon #set-map-hide_after_min").exists()).toBe(false);
  });

  it("changes the settings and shows an error under the field", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    await wrapper.find("#set-serial-baud").setValue("5");
    await wrapper.find("#pane-settings form").trigger("submit");
    expect(socket.sent).toContainEqual({ cmd: "set_config", values: { "serial/baud": "5" } });
    socket.say({ type: "error", text: "set_config: serial/baud: 5 is not between 300 and 921600" });
    await flushPromises();
    expect(wrapper.find("#set-serial-baud").element.closest(".field")?.textContent).toContain("5 is not between 300 and 921600");
    expect(wrapper.find(".toast").text()).toContain("serial/baud");
  });

  describe("messages not seen", () => {
    const show = (state: "visible" | "hidden") => {
      Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
      document.dispatchEvent(new Event("visibilitychange"));
    };

    it("counts them in the title of the browser tab, in the header and on the Messages tab", async () => {
      const { wrapper } = await open();
      expect(document.title).toBe("(2) NeoAPRS");
      expect(wrapper.find(".headmail").text()).toContain("2");
      expect(tabButton(wrapper, "Messages")?.find(".badge").text()).toBe("2");
    });

    it("shows the count on the handle of the folded panel, and on no other", async () => {
      const { wrapper } = await open();
      expect(wrapper.find(".fold-badge").exists()).toBe(false);
      await wrapper.find(".panel-fold").trigger("click");
      expect(wrapper.find(".fold-badge").text()).toBe("2");
      await wrapper.find(".panel-fold").trigger("click");
      expect(wrapper.find(".fold-badge").exists()).toBe(false);
    });

    it("opens the Messages tab on the newest conversation with something new from the header, and the title counts down", async () => {
      const { wrapper } = await open();
      await wrapper.find(".panel-fold").trigger("click");
      await wrapper.find(".headmail").trigger("click");
      expect(wrapper.find(".panel").classes()).not.toContain("collapsed");
      expect(wrapper.find("[aria-selected='true']").text()).toContain("Messages");
      expect(wrapper.find(".conv.active .conv-call").text()).toBe("OH2PU-9");
      expect(document.title).toBe("(1) NeoAPRS");
      expect(wrapper.find(".conv.fresh .conv-call").text()).toBe("OH2RDG");
    });

    it("keeps counting a message in the open conversation while the page is hidden, and has seen it when the page is back", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Messages")?.trigger("click");
      await wrapper.find("#pane-messages .conv").trigger("click");
      expect(document.title).toBe("(1) NeoAPRS");
      show("hidden");
      socket.say({ type: "patch", topic: "messages", rev: 1, ops: [{ op: "set", key: "4", value: incoming(4, "OH2PU-9", { text: "Hello again" }) }] });
      await flushPromises();
      expect(document.title).toBe("(2) NeoAPRS");
      show("visible");
      await flushPromises();
      expect(document.title).toBe("(1) NeoAPRS");
    });

    it("keeps counting while the panel is folded or another tab is on show, with the conversation open", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Messages")?.trigger("click");
      await wrapper.find("#pane-messages .conv").trigger("click");
      await tabButton(wrapper, "Packets")?.trigger("click");
      socket.say({ type: "patch", topic: "messages", rev: 1, ops: [{ op: "set", key: "4", value: incoming(4, "OH2PU-9") }] });
      await flushPromises();
      expect(document.title).toBe("(2) NeoAPRS");
      await tabButton(wrapper, "Messages")?.trigger("click");
      expect(document.title).toBe("(1) NeoAPRS");
      await wrapper.find(".panel-fold").trigger("click");
      socket.say({ type: "patch", topic: "messages", rev: 2, ops: [{ op: "set", key: "5", value: incoming(5, "OH2PU-9") }] });
      await flushPromises();
      expect(document.title).toBe("(2) NeoAPRS");
    });

    it("has no Delete button on a message, and the daemon is not asked to delete one", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Messages")?.trigger("click");
      await wrapper.find("#pane-messages .conv").trigger("click");
      expect(wrapper.findAll("#pane-messages .msg").length).toBeGreaterThan(0);
      expect(wrapper.find("#pane-messages .msg-delete").exists()).toBe(false);
      expect(JSON.stringify(socket.sent)).not.toContain("message_delete");
    });
  });

  describe("the Bulletins tab", () => {
    const board = {
      "OH2XYZ/BLN1": bulletin("BLN1", { first_heard: ago(600), last_heard: ago(300), times_heard: 3, text: "Road closed" }),
      "OH2ABC/QST": bulletin("QST", { sender: "OH2ABC", kind: "group", first_heard: ago(100), last_heard: ago(100), text: "Club news" }),
    };
    const sayBoard = async (socket: ReturnType<typeof FakeSocket.last>) => {
      socket.say({ type: "state", topic: "bulletins", rev: 0, value: board });
      await flushPromises();
    };
    const badge = (wrapper: VueWrapper) => tabButton(wrapper, "Bulletins")?.find(".badge");

    it("comes after Email and shows the board, with a badge of what is new until it has been on show", async () => {
      const { wrapper, socket } = await open();
      expect(wrapper.findAll("[role='tab']").map((t) => t.text().replace(/\s*\d+$/, ""))).toEqual([
        "Stations",
        "Packets",
        "Messages",
        "Email",
        "Bulletins",
        "Beacon",
        "TNC",
        "Settings",
      ]);
      await sayBoard(socket);
      expect(badge(wrapper)?.text()).toBe("2");
      expect(badge(wrapper)?.attributes("title")).toBe("2 new bulletins");
      await tabButton(wrapper, "Bulletins")?.trigger("click");
      expect(badge(wrapper)?.exists()).toBeFalsy();
      expect(wrapper.findAll("#pane-bulletins .bulletin-text").map((t) => t.text())).toEqual(["Road closed", "Club news"]);
      expect(wrapper.findAll("#pane-bulletins .board-title").map((t) => t.text())).toEqual(["Bulletins 1", "Group messages 1"]);
    });

    it("counts a bulletin that comes while another tab is on show, on the handle of the folded panel too, and not one that comes while it is looked at", async () => {
      const { wrapper, socket } = await open();
      await sayBoard(socket);
      await tabButton(wrapper, "Bulletins")?.trigger("click");
      socket.say({
        type: "patch",
        topic: "bulletins",
        rev: 1,
        ops: [{ op: "set", key: "OH2DEF/BLN2", value: bulletin("BLN2", { sender: "OH2DEF", first_heard: ago(5) }) }],
      });
      await flushPromises();
      expect(badge(wrapper)?.exists()).toBeFalsy();
      await tabButton(wrapper, "Stations")?.trigger("click");
      socket.say({
        type: "patch",
        topic: "bulletins",
        rev: 2,
        ops: [{ op: "set", key: "OH2GHI/BLN3", value: bulletin("BLN3", { sender: "OH2GHI", first_heard: ago(2) }) }],
      });
      await flushPromises();
      expect(badge(wrapper)?.text()).toBe("1");
      await wrapper.find(".panel-fold").trigger("click");
      expect(wrapper.find(".fold-badge").text()).toBe("3");
      expect(wrapper.find(".fold-badge").attributes("title")).toBe("2 messages not seen yet, 1 new bulletin");
    });

    it("deletes a board entry after two presses of its x, with one command", async () => {
      const { wrapper, socket } = await open();
      await sayBoard(socket);
      await tabButton(wrapper, "Bulletins")?.trigger("click");
      const x = () => wrapper.find("#pane-bulletins .bulletin-delete");
      await x().trigger("click");
      expect(x().text()).toBe("sure?");
      expect(JSON.stringify(socket.sent)).not.toContain("bulletin_delete");
      await x().trigger("click");
      expect(socket.sent.filter((c) => (c as { cmd?: string }).cmd === "bulletin_delete")).toHaveLength(1);
    });

    it("forgets a bulletin that was deleted", async () => {
      const { wrapper, socket } = await open();
      await sayBoard(socket);
      await tabButton(wrapper, "Bulletins")?.trigger("click");
      socket.say({ type: "patch", topic: "bulletins", rev: 1, ops: [{ op: "del", key: "OH2XYZ/BLN1" }] });
      await flushPromises();
      expect(wrapper.findAll("#pane-bulletins .bulletin")).toHaveLength(1);
    });
  });

  describe("a conversation", () => {
    const conv = (wrapper: VueWrapper, call: string) => wrapper.findAll("#pane-messages .conv").find((c) => c.find(".conv-call").text() === call);
    const x = (wrapper: VueWrapper, call: string) =>
      wrapper
        .findAll("#pane-messages .conv-item")
        .find((c) => c.find(".conv-call").text() === call)
        ?.find(".conv-delete");

    it("is a toggle: a click on the open one closes its thread, a click on another opens that one", async () => {
      const { wrapper } = await open();
      await tabButton(wrapper, "Messages")?.trigger("click");
      expect(wrapper.find("#pane-messages .conv.active").exists()).toBe(false);
      await conv(wrapper, "OH2RDG")?.trigger("click");
      expect(wrapper.findAll("#pane-messages .msg")).toHaveLength(2);
      expect(wrapper.find<HTMLInputElement>("#msg-to").element.value).toBe("OH2RDG");
      await conv(wrapper, "OH2PU-9")?.trigger("click");
      expect(wrapper.find("#pane-messages .conv.active .conv-call").text()).toBe("OH2PU-9");
      expect(wrapper.find<HTMLInputElement>("#msg-to").element.value).toBe("OH2PU-9");
      await conv(wrapper, "OH2PU-9")?.trigger("click");
      expect(wrapper.find("#pane-messages .conv.active").exists()).toBe(false);
      expect(wrapper.findAll("#pane-messages .msg")).toHaveLength(0);
      expect(wrapper.find("#pane-messages .thread").text()).toBe("");
      expect(wrapper.find<HTMLInputElement>("#msg-to").element.value).toBe("");
      expect(wrapper.findAll("#pane-messages .conv")).toHaveLength(2);
    });

    it("is opened by the Message button of the station's card, which opens it again rather than toggling it", async () => {
      const { wrapper } = await open();
      await wrapper
        .findAll("#pane-stations tbody tr")
        .find((r) => r.text().includes("OH2PU-9"))
        ?.trigger("click");
      const message = () => wrapper.findAll(".card .btn").find((b) => b.text() === "Message");
      await message()?.trigger("click");
      expect(wrapper.find("[aria-selected='true']").text()).toContain("Messages");
      expect(wrapper.find("#pane-messages .conv.active .conv-call").text()).toBe("OH2PU-9");
      await message()?.trigger("click");
      expect(wrapper.find("#pane-messages .conv.active .conv-call").text()).toBe("OH2PU-9");
      await conv(wrapper, "OH2PU-9")?.trigger("click");
      expect(wrapper.find("#pane-messages .conv.active").exists()).toBe(false);
      await message()?.trigger("click");
      expect(wrapper.find("#pane-messages .conv.active .conv-call").text()).toBe("OH2PU-9");
    });

    it("is deleted after two clicks on its x, with one command, and its thread closes if it was the open one", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Messages")?.trigger("click");
      await conv(wrapper, "OH2RDG")?.trigger("click");
      await x(wrapper, "OH2RDG")?.trigger("click");
      expect(x(wrapper, "OH2RDG")?.text()).toBe("sure?");
      expect(JSON.stringify(socket.sent)).not.toContain("conversation_delete");
      await x(wrapper, "OH2RDG")?.trigger("click");
      expect(socket.sent).toContainEqual({ cmd: "conversation_delete", call: "OH2RDG" });
      expect(wrapper.find("#pane-messages .conv.active").exists()).toBe(false);
      expect(wrapper.find<HTMLInputElement>("#msg-to").element.value).toBe("");
      socket.say({
        type: "patch",
        topic: "messages",
        rev: 1,
        ops: [
          { op: "del", key: "1" },
          { op: "del", key: "2" },
        ],
      });
      await flushPromises();
      expect(wrapper.findAll("#pane-messages .conv-call").map((c) => c.text())).toEqual(["OH2PU-9"]);
    });

    it("keeps the open thread when another conversation is deleted", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Messages")?.trigger("click");
      await conv(wrapper, "OH2RDG")?.trigger("click");
      await x(wrapper, "OH2PU-9")?.trigger("click");
      await x(wrapper, "OH2PU-9")?.trigger("click");
      expect(socket.sent).toContainEqual({ cmd: "conversation_delete", call: "OH2PU-9" });
      expect(wrapper.find("#pane-messages .conv.active .conv-call").text()).toBe("OH2RDG");
    });

    it("has an overheard pair deleted after two clicks on its x with one command, when the overheard rows are listed", async () => {
      const { wrapper, socket } = await open();
      const heard = message(20, { direction: "in", state: "overheard", from_call: "OH2AAA", to_call: "OH2BBB", text: "chatter", attempts: 0 });
      socket.say({ type: "patch", topic: "messages", rev: 1, ops: [{ op: "set", key: "20", value: heard }] });
      await flushPromises();
      await tabButton(wrapper, "Messages")?.trigger("click");
      expect(x(wrapper, "OH2AAA > OH2BBB")).toBeUndefined();
      await wrapper.find<HTMLInputElement>("#pane-messages .toolbar input").setValue(true);
      await x(wrapper, "OH2AAA > OH2BBB")?.trigger("click");
      expect(x(wrapper, "OH2AAA > OH2BBB")?.text()).toBe("sure?");
      expect(JSON.stringify(socket.sent)).not.toContain("overheard_delete");
      await x(wrapper, "OH2AAA > OH2BBB")?.trigger("click");
      expect(socket.sent).toContainEqual({ cmd: "overheard_delete", from_call: "OH2AAA", to_call: "OH2BBB" });
      expect(JSON.stringify(socket.sent)).not.toContain("conversation_delete");
    });
  });

  describe("the Email tab", () => {
    const gateway = (id: number, extra = {}) => incoming(id, "EMAIL-2", { text: "Msg sent to jane@example.com", ...extra });
    const say = async (socket: ReturnType<typeof FakeSocket.last>, rev: number, ...rows: ReturnType<typeof incoming>[]) => {
      socket.say({ type: "patch", topic: "messages", rev, ops: rows.map((r) => ({ op: "set", key: String(r.id), value: r })) });
      await flushPromises();
    };
    const badge = (wrapper: VueWrapper) => tabButton(wrapper, "Email")?.find(".badge");

    it("sends mail as a message to EMAIL-2 and the three commands as their texts, and keeps the addressee in the list", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Email")?.trigger("click");
      await wrapper.find("#mail-to").setValue("jane@example.com");
      await wrapper.find("#mail-text").setValue("Hello");
      await wrapper.find("#pane-email form.compose").trigger("submit");
      expect(socket.sent).toContainEqual({ cmd: "set_station_attempts", call: "EMAIL-2", attempts: 2 });
      expect(JSON.stringify(socket.sent)).not.toContain("jane@example.com Hello");
      socket.say({
        type: "patch",
        topic: "station_prefs",
        rev: 1,
        ops: [{ op: "set", key: "EMAIL-2", value: { path: null, hide_after_min: null, attempts: 2, rf_only: false } }],
      });
      await flushPromises();
      expect(socket.sent).toContainEqual({ cmd: "send_message", to: "EMAIL-2", text: "jane@example.com Hello" });
      expect(wrapper.find<HTMLInputElement>("#pane-email .attempts-input").element.value).toBe("2");
      expect(wrapper.findAll("#pane-email .address-pick").map((b) => b.text())).toEqual(["jane@example.com"]);
      expect(JSON.parse(localStorage.getItem("NeoAPRS.emailto") ?? "[]")).toEqual(["jane@example.com"]);
      const tools = wrapper.findAll("#pane-email .mail-tools > button");
      await tools[0]?.trigger("click");
      await wrapper.find("#mail-shortcut").setValue("me");
      await wrapper.find("#pane-email .mail-shortcut").trigger("submit");
      await tools[2]?.trigger("click");
      await wrapper.find("#mail-to").setValue("jane");
      await tools[1]?.trigger("click");
      await tools[1]?.trigger("click");
      expect(socket.sent.slice(-3)).toEqual([
        { cmd: "send_message", to: "EMAIL-2", text: "me L" },
        { cmd: "send_message", to: "EMAIL-2", text: "get" },
        { cmd: "send_message", to: "EMAIL-2", text: "jane R" },
      ]);
    });

    it("shows the gateway's attempts beside the buttons and sends the change", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Email")?.trigger("click");
      const input = wrapper.find<HTMLInputElement>("#pane-email .attempts-input");
      expect(input.attributes("placeholder")).toBe("(default: 6)");
      await input.setValue("1");
      expect(socket.sent).toContainEqual({ cmd: "set_station_attempts", call: "EMAIL-2", attempts: 1 });
    });

    it("shows the thread with the gateway there and leaves it out of the Messages tab and its count", async () => {
      const { wrapper, socket } = await open();
      await say(socket, 1, message(10, { to_call: "EMAIL-2", text: "me hello" }), gateway(11));
      expect(wrapper.findAll("#pane-email .msg").map((m) => m.find(".msg-text").text())).toEqual(["me hello", "Msg sent to jane@example.com"]);
      expect(wrapper.findAll("#pane-messages .conv-call").map((c) => c.text())).toEqual(["OH2PU-9", "OH2RDG"]);
      expect(tabButton(wrapper, "Messages")?.find(".badge").text()).toBe("2");
      expect(wrapper.find(".headmail").text()).toContain("2");
    });

    it("counts the gateway's messages on the Email tab, in the title and on the folded handle, until the tab is on show", async () => {
      const { wrapper, socket } = await open();
      expect(badge(wrapper)?.exists()).toBe(false);
      await say(socket, 1, gateway(11), gateway(12));
      expect(badge(wrapper)?.text()).toBe("2");
      expect(badge(wrapper)?.attributes("title")).toBe("2 messages not seen yet");
      expect(document.title).toBe("(4) NeoAPRS");
      await wrapper.find(".panel-fold").trigger("click");
      expect(wrapper.find(".fold-badge").text()).toBe("4");
      await wrapper.find(".panel-fold").trigger("click");
      await tabButton(wrapper, "Email")?.trigger("click");
      expect(badge(wrapper)?.exists()).toBe(false);
      expect(document.title).toBe("(2) NeoAPRS");
    });

    it("keeps counting while the page is hidden or the panel folded, with the Email tab in front", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Email")?.trigger("click");
      Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" });
      document.dispatchEvent(new Event("visibilitychange"));
      await say(socket, 1, gateway(11));
      expect(badge(wrapper)?.text()).toBe("1");
      Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" });
      document.dispatchEvent(new Event("visibilitychange"));
      await flushPromises();
      expect(badge(wrapper)?.exists()).toBe(false);
      await wrapper.find(".panel-fold").trigger("click");
      await say(socket, 2, gateway(12));
      expect(wrapper.find(".fold-badge").text()).toBe("3");
    });

    it("is opened by the Message button of the gateway's station card", async () => {
      const { wrapper, socket } = await open();
      socket.say({ type: "patch", topic: "stations", rev: 1, ops: [{ op: "set", key: "EMAIL-2", value: station("EMAIL-2", { lat: null, lon: null }) }] });
      await flushPromises();
      await wrapper
        .findAll("#pane-stations tbody tr")
        .find((r) => r.text().includes("EMAIL-2"))
        ?.trigger("click");
      await wrapper
        .findAll(".card .btn")
        .find((b) => b.text() === "Message")
        ?.trigger("click");
      expect(wrapper.find("[aria-selected='true']").text()).toContain("Email");
    });
  });

  it("remembers the tab and the folding of the panel and its width", async () => {
    const { wrapper } = await open();
    await tabButton(wrapper, "Packets")?.trigger("click");
    await wrapper.find("[role='separator']").trigger("keydown", { key: "ArrowLeft" });
    await wrapper.find(".panel-fold").trigger("click");
    expect(localStorage.getItem("NeoAPRS.tab")).toBe("packets");
    expect(localStorage.getItem("NeoAPRS.panel")).toBe("collapsed");
    expect(Number(localStorage.getItem("NeoAPRS.panelwidth"))).toBeGreaterThan(480);
    wrapper.unmount();
    const again = await open();
    expect(again.wrapper.find(".panel").classes()).toContain("collapsed");
    await again.wrapper.find(".panel-fold").trigger("click");
    expect(again.wrapper.find("[aria-selected='true']").text()).toBe("Packets");
  });

  it("remembers a panel wider than 900 px, shows it as wide as the window allows, and keeps it for a wider window", async () => {
    const wide = window.innerWidth;
    localStorage.setItem("NeoAPRS.panelwidth", "1200");
    const { wrapper } = await open();
    expect(wrapper.find(".panel").attributes("style")).toContain(`--panel-width: ${Math.min(Math.floor(wide * 0.8), wide - 360)}px`);
    window.innerWidth = 2000;
    window.dispatchEvent(new Event("resize"));
    await flushPromises();
    expect(wrapper.find(".panel").attributes("style")).toContain("--panel-width: 1200px");
    expect(localStorage.getItem("NeoAPRS.panelwidth")).toBe("1200");
    window.innerWidth = wide;
  });

  it("works without localStorage", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { wrapper } = await open();
    await tabButton(wrapper, "TNC")?.trigger("click");
    expect(wrapper.find("[aria-selected='true']").text()).toBe("TNC");
    vi.restoreAllMocks();
  });

  it("downloads the map from the Settings tab: the buttons send the commands and the progress follows the topic", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "map", rev: 0, value: mapState() });
    await flushPromises();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const download = wrapper.findAll("#pane-settings .mapfetch button").find((b) => b.text() === "Download");
    await download?.trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "map_fetch" });
    socket.say({
      type: "patch",
      topic: "map",
      rev: 1,
      ops: [{ op: "replace", value: mapState({ state: "downloading", step: "world", percent: 42, blocked: "a map job is running" }) }],
    });
    await flushPromises();
    expect(wrapper.find("#pane-settings .mapfetch-progress").text()).toBe("World map 42%");
  });

  it("offers the download on the map when there is no base map, and the button opens the Settings tab", async () => {
    fakeState.archive = false;
    const { wrapper } = await open();
    expect(wrapper.find(".mapnote span").text()).toBe("No base map");
    await wrapper.find(".mapnote button").trigger("click");
    expect(tabButton(wrapper, "Settings")?.attributes("aria-selected")).toBe("true");
  });

  it("sets the map's style again when the daemon has made the files", async () => {
    const { socket } = await open();
    socket.say({ type: "state", topic: "map", rev: 0, value: mapState({ state: "downloading", step: "area", percent: 50 }) });
    await flushPromises();
    expect(FakeMap.last().styles).toHaveLength(1);
    socket.say({
      type: "patch",
      topic: "map",
      rev: 1,
      ops: [{ op: "replace", value: mapState({ state: "ready", detail: mapFile(), world: mapFile({ name: "basemap-world.pmtiles" }) }) }],
    });
    await flushPromises();
    expect(FakeMap.last().styles).toHaveLength(2);
  });
});
