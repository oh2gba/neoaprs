import "@/test/mockmap";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App.vue";
import { FakeMap, FakeMarker, fakeState, resetFakes } from "@/test/fakemap";
import { FakeSocket } from "@/test/fakesocket";
import { stubWidth } from "@/test/width";
import { FakeAudioContext, FakeNotification, openedAt, setSeen, stubBrowser } from "@/test/fakealert";
import {
  ago,
  bulletin,
  configValues,
  hello,
  incoming,
  NOW,
  mapFile,
  mapState,
  message,
  ownBulletin,
  ownObject,
  packet,
  station,
  status,
  tncState,
} from "@/test/fixtures";

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
  socket.say(hello());
  socket.say({ type: "state", topic: "stations", rev: 0, value: stations });
  socket.say({ type: "state", topic: "packets", rev: 0, value: { "1": packet(1), "2": packet(2, { summary: "second" }) } });
  socket.say({ type: "state", topic: "tnc", rev: 0, value: tncState() });
  socket.say({ type: "state", topic: "config", rev: 0, value: configValues() }); // (the clock stands at the fixtures' time, so nothing times out)
  socket.say({ type: "state", topic: "messages", rev: 0, value: messages });
  socket.say({ type: "state", topic: "station_prefs", rev: 0, value: { OH2RDG: { path: "OH2RCH-2", hide_after_min: null, rf_only: false } } });
  socket.say(status());
  await flushPromises();
  return { wrapper, socket };
}

const tabButton = (wrapper: VueWrapper, title: string) => wrapper.findAll("[role='tab']").find((t) => t.text().startsWith(title));

// the panel is 720 px wide, so that the Messages tab has the list beside the conversation; the narrow layout is tried where a test says so
let panelWidth: ReturnType<typeof stubWidth>;
beforeEach(() => {
  panelWidth = stubWidth(720);
  window.innerWidth = 1400; // a desktop (the tests of the other sizes set their own)
  window.innerHeight = 900;
  FakeSocket.all = [];
  resetFakes();
  localStorage.clear();
  sessionStorage.clear();
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.useFakeTimers({ toFake: ["Date"] }); // (the clock stands at the fixtures' time: a station times out after 3 hours)
  vi.setSystemTime(NOW);
});
afterEach(() => {
  panelWidth.restore();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  openedAt("127.0.0.1");
  Reflect.deleteProperty(document, "visibilityState");
  document.title = "NeoAPRS";
  document.body.replaceChildren();
});

describe("App", () => {
  it("opened on the Settings tab, shows no 'not connected' toast and asks for the ports once the daemon is connected", async () => {
    localStorage.setItem("NeoAPRS.tab", "settings");
    const wrapper = mount(App, { attachTo: document.body });
    await flushPromises();
    const socket = FakeSocket.last();
    expect(socket.sent.filter((c) => (c as { cmd: string }).cmd === "list_ports")).toHaveLength(0);
    socket.say(hello());
    socket.say({ type: "state", topic: "config", rev: 0, value: configValues() });
    await flushPromises();
    expect(socket.sent.filter((c) => (c as { cmd: string }).cmd === "list_ports")).toHaveLength(1);
    expect(wrapper.text()).not.toContain("Not connected to the daemon");
  });

  it("says Connecting… under the panel, then nothing of the radio; the header has the title and not our call", async () => {
    const wrapper = mount(App, { attachTo: document.body });
    await flushPromises();
    expect(wrapper.find(".panelfoot").text()).toContain("Connecting…");
    const socket = FakeSocket.last();
    socket.say(hello());
    socket.say({ type: "state", topic: "tnc", rev: 0, value: tncState() });
    socket.say({ type: "state", topic: "config", rev: 0, value: configValues() });
    await flushPromises();
    const header = wrapper.find(".appheader").text();
    expect(header).toBe("NeoAPRS");
    expect(wrapper.find(".appheader a").attributes("href")).toBe("https://oh2gba.github.io/neoaprs/");
    const foot = wrapper.find(".panelfoot").text();
    expect(foot).toBe(`NeoAPRS ${hello().version}`);
    expect(wrapper.find("#pane-settings").element.parentElement?.lastElementChild).toBe(wrapper.find(".panelfoot").element);
    expect(wrapper.find(".mapwrap .panelfoot").exists()).toBe(false);
  });

  it("shows the radio under the panel only while it is not connected, and the line does not change", async () => {
    const { wrapper, socket } = await open();
    const foot = wrapper.find(".panelfoot");
    expect(foot.find("button.status").exists()).toBe(false);
    socket.say({ type: "state", topic: "tnc", rev: 1, value: tncState({ state: "waiting", problem: "no radio found", describe: "waiting" }) });
    await flushPromises();
    expect(wrapper.find(".panelfoot").element).toBe(foot.element);
    expect(foot.find("button.status").text()).toBe("Radio: not connected");
    socket.say({ type: "state", topic: "tnc", rev: 2, value: tncState() });
    await flushPromises();
    expect(foot.find("button.status").exists()).toBe(false);
    expect(wrapper.find(".appheader").text()).not.toMatch(/radio/i);
  });

  it("says daemon offline when the socket closes, and connects again", async () => {
    const { wrapper, socket } = await open();
    vi.useFakeTimers();
    socket.hangUp();
    await flushPromises();
    expect(wrapper.find(".panelfoot .link-bad").text()).toBe("Daemon offline");
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
      value: configValues({ "station/call": "", "station/lat": "", "station/lon": "" }),
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
      value: configValues({ "station/call": "", "station/lat": "", "station/lon": "", "serial/baud": "" }),
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
    await next();
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
          "beacon/interval_min": "30",
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
    socket.say({ type: "error", text: "set_config: station/call: 'OH2ABC' is already in use" });
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
    await wrapper.find(".setup .mapfetch button").trigger("click");
    expect(commands().filter((c) => c === "set_config")).toHaveLength(1);
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
    await wrapper.find(".setup .mapfetch button").trigger("click");
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
    const before = (seconds: number) => new Date(Date.now() - seconds * 1000).toISOString();
    socket.say({
      type: "patch",
      topic: "stations",
      rev: 1,
      ops: [
        { op: "set", key: "OH2RDG", value: { ...stations.OH2RDG, last_position_at: before(4 * 3600) } },
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

  it("shows the radio link at the top of the TNC group of the Settings tab and asks for a reconnect", async () => {
    const { wrapper, socket } = await open();
    expect(tabButton(wrapper, "TNC")).toBeUndefined();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const group = wrapper.find("#pane-settings fieldset");
    expect(group.find("legend").text()).toBe("TNC");
    expect(group.find(".radiostatus .tncstatus").text()).toMatch(/^Last packet /);
    await group.find(".radiostatus button").trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "tnc_reconnect" });
  });

  it("opens the Settings tab, where the radio is, from the radio state under the panel", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "tnc", rev: 1, value: tncState({ state: "connecting", problem: "", describe: "listening on /dev/brainbox_1" }) });
    await flushPromises();
    await tabButton(wrapper, "Stations")?.trigger("click");
    await wrapper.find(".panelfoot button.status").trigger("click");
    expect(wrapper.find("[aria-selected='true']").text()).toContain("Settings");
  });

  it("sends a beacon from the Beacon tab after two clicks, and shows when the last one went out", async () => {
    const { wrapper, socket } = await open();
    socket.say(status({ beacon_interval_min: 15, beacon_last_sent: ago(60), beacon_next_due: new Date(Date.now() + 840_000).toISOString() }));
    await flushPromises();
    await tabButton(wrapper, "Beacon")?.trigger("click");
    expect(wrapper.find("#pane-beacon .sendrow").text()).toContain("Last beacon1 min ago");
    await wrapper.find("#pane-beacon .sendrow button").trigger("click");
    expect(socket.sent).not.toContainEqual({ cmd: "beacon_now" });
    await wrapper.find("#pane-beacon .sendrow button").trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "beacon_now" });
  });

  it("sends the status from the Beacon tab after two clicks once there is a status, and not before", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Beacon")?.trigger("click");
    expect(wrapper.findAll("#pane-beacon .sendrow button").map((b) => b.text())).toEqual(["Beacon now"]);
    socket.say({
      type: "state",
      topic: "config",
      rev: 1,
      value: configValues({ "status/source": "text", "station/status": "QRV 145.500" }),
    });
    await flushPromises();
    expect(wrapper.findAll("#pane-beacon .sendrow button").map((b) => b.text())).toEqual(["Beacon now", "Send status now"]);
    await wrapper.findAll("#pane-beacon .sendrow button")[1]?.trigger("click");
    expect(socket.sent).not.toContainEqual({ cmd: "status_now" });
    await wrapper.findAll("#pane-beacon .sendrow button")[1]?.trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "status_now" });
    expect(socket.sent).not.toContainEqual({ cmd: "beacon_now" });
  });

  it("previews the beacon packet as it is typed and applies the beacon's settings from the Beacon tab when each field is left", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Beacon")?.trigger("click");
    expect(wrapper.find("#pane-beacon .beacon-preview code").text()).toBe("OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS");
    await wrapper.find("#pane-beacon #set-station-comment").setValue("hello");
    await wrapper.find("#pane-beacon #set-beacon-path").setValue("");
    expect(wrapper.find("#pane-beacon .beacon-preview code").text()).toBe("OH2GBA>APZNEO:=6010.20N/02456.40E-hello");
    expect(socket.sent.filter((c) => (c as { cmd: string }).cmd === "set_config")).toEqual([]);
    await wrapper.find("#pane-beacon #set-station-comment").trigger("blur");
    expect(socket.sent).toContainEqual({ cmd: "set_config", values: { "station/comment": "hello" } });
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
      ops: [{ op: "set", key: "OH2PU-9", value: { path: null, hide_after_min: 45, rf_only: false } }],
    });
    await flushPromises();
    expect(field().element.value).toBe("45");
    await wrapper.find(".card .timeoutbox .use-default").trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "clear_station_timeout", call: "OH2PU-9" });
    await tabButton(wrapper, "Messages")?.trigger("click");
    await wrapper.find("#pane-messages .conv").trigger("click");
    expect(wrapper.find("#pane-messages .timeout-input").exists()).toBe(false); // the map timeout is the station's, not the conversation's
  });

  it("has the message settings in the conversation the card's Message button opens, none on the card; RF only is sent and follows the daemon", async () => {
    const { wrapper, socket } = await open();
    await wrapper
      .findAll("#pane-stations tbody tr")
      .find((r) => r.text().includes("OH2PU-9"))
      ?.trigger("click");
    expect(wrapper.find(".card .rfonly").exists()).toBe(false);
    expect(wrapper.find(".card .use-suggested").exists()).toBe(false);
    await wrapper
      .findAll(".card .btn")
      .find((b) => b.text() === "Message")
      ?.trigger("click");
    await wrapper.find("#pane-messages .convo-head .route-button").trigger("click");
    const header = wrapper.find<HTMLInputElement>("#pane-messages .route-box .rfonly input");
    expect(wrapper.findAll("#pane-messages .route-box label").map((l) => l.text())).toEqual(["Path", "RF only"]);
    await header.setValue(true);
    expect(socket.sent).toContainEqual({ cmd: "set_station_rf_only", call: "OH2PU-9", on: true });
    socket.say({
      type: "patch",
      topic: "station_prefs",
      rev: 1,
      ops: [{ op: "set", key: "OH2PU-9", value: { path: null, hide_after_min: null, rf_only: true } }],
    });
    await flushPromises();
    expect(wrapper.find<HTMLInputElement>("#pane-messages .route-box .rfonly input").element.checked).toBe(true);
    await wrapper.find<HTMLInputElement>("#pane-messages .route-box .rfonly input").setValue(false);
    expect(socket.sent).toContainEqual({ cmd: "set_station_rf_only", call: "OH2PU-9", on: false });
  });

  it("has the map's radius on the Settings tab and the station and beacon keys on the Beacon tab, none twice", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "config", rev: 1, value: configValues() });
    await flushPromises();
    expect(wrapper.find("#pane-settings #set-map-radius_km").exists()).toBe(true);
    expect(wrapper.find("#pane-settings #set-map-hide_after_min").exists()).toBe(false);
    expect(wrapper.find("#pane-settings #set-station-call").exists()).toBe(false);
    expect(wrapper.find("#pane-beacon #set-station-call").exists()).toBe(true);
    expect(wrapper.find("#pane-beacon #set-map-radius_km").exists()).toBe(false);
  });

  it("changes the settings as they are made and shows the daemon's refusal under the field", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    await wrapper.find("#set-messages-alert_command").setValue("x".repeat(1001));
    await wrapper.find("#set-messages-alert_command").trigger("blur");
    expect(socket.sent).toContainEqual({ cmd: "set_config", values: { "messages/alert_command": "x".repeat(1001) } });
    socket.say({ type: "error", text: "set_config: messages/alert_command: 1001 characters is more than the 1000 allowed" });
    await flushPromises();
    expect(wrapper.find("#set-messages-alert_command").element.closest(".field")?.textContent).toContain("more than the 1000 allowed");
    expect(wrapper.find<HTMLInputElement>("#set-messages-alert_command").element.value).toBe("x".repeat(1001));
    expect(wrapper.find(".toast").text()).toContain("messages/alert_command");
  });

  describe("settings that apply as they are changed", () => {
    const sets = (socket: FakeSocket) => socket.sent.filter((c) => (c as { cmd: string }).cmd === "set_config");
    const toast = (wrapper: VueWrapper) => wrapper.find(".toast.undo");
    const told = (socket: FakeSocket, changes: Record<string, string>) =>
      socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ ...changes }) });

    it("has one queue for the Settings tab and the Beacon tab: the second change waits for the answer to the first", async () => {
      const { wrapper, socket } = await open();
      await wrapper.find("#pane-settings #set-digi-enabled").setValue(true);
      await wrapper.find("#pane-beacon #set-beacon-path").setValue("WIDE2-2");
      await wrapper.find("#pane-beacon #set-beacon-path").trigger("blur");
      expect(sets(socket)).toEqual([{ cmd: "set_config", values: { "digi/enabled": "true" } }]);
      told(socket, { "digi/enabled": "true" });
      await flushPromises();
      expect(sets(socket)).toHaveLength(2);
      expect(sets(socket)[1]).toEqual({ cmd: "set_config", values: { "beacon/path": "WIDE2-2" } });
    });

    it("offers Undo for the change that was made, and Undo sends the old values in one set_config", async () => {
      const { wrapper, socket } = await open();
      await wrapper.find("#pane-settings #set-digi-enabled").setValue(true);
      expect(toast(wrapper).exists()).toBe(false);
      told(socket, { "digi/enabled": "true" });
      await flushPromises();
      expect(toast(wrapper).text()).toContain("Digipeater changed");
      await toast(wrapper).find(".undo-button").trigger("click");
      expect(sets(socket)[1]).toEqual({ cmd: "set_config", values: { "digi/enabled": "false" } });
      expect(toast(wrapper).exists()).toBe(false);
      told(socket, {});
      await flushPromises();
      expect(toast(wrapper).exists()).toBe(false);
    });

    it("lets the toast go after ten seconds, and covers the latest of several quick changes", async () => {
      const { wrapper, socket } = await open();
      vi.useFakeTimers();
      await wrapper.find("#pane-settings #set-digi-enabled").setValue(true);
      told(socket, { "digi/enabled": "true" });
      await flushPromises();
      await wrapper.find("#pane-settings #set-map-radius_km").setValue("200");
      await wrapper.find("#pane-settings #set-map-radius_km").trigger("blur");
      expect(toast(wrapper).exists()).toBe(false);
      told(socket, { "digi/enabled": "true", "map/radius_km": "200" });
      await flushPromises();
      expect(toast(wrapper).text()).toContain("Map radius changed");
      vi.advanceTimersByTime(10001);
      await flushPromises();
      expect(toast(wrapper).exists()).toBe(false);
      vi.useRealTimers();
    });

    it("asks before the network is turned off on a page opened from another device", async () => {
      const { wrapper, socket } = await open();
      told(socket, { "web/network": "true", "web/key": "k7m2-x9pq-4hrt" });
      await flushPromises();
      openedAt("192.168.1.20");
      await wrapper.find("#pane-settings #set-web-network").setValue(false);
      expect(wrapper.find("#pane-settings .confirm-row").text()).toContain("This device will lose the page. Turn off?");
      expect(sets(socket)).toEqual([]);
    });
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
      expect(wrapper.findAll("#pane-messages .bubble").length).toBeGreaterThan(0);
      expect(wrapper.find("#pane-messages .bubble-delete").exists()).toBe(false);
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
        "Messages",
        "Stations",
        "Email",
        "Bulletins",
        "Objects",
        "Beacon",
        "Packets",
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
      // the handle counts the messages not seen, as the header does: a new bulletin is not one
      expect(wrapper.find(".fold-badge").text()).toBe("2");
      expect(wrapper.find(".fold-badge").attributes("title")).toBe("2 messages not seen yet");
      expect(wrapper.find(".headmail").text()).toContain("2");
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

  describe("posting to the board", () => {
    it("posts a bulletin from the box on the Bulletins tab, with one command, and shows ours on the board when the daemon says so", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Bulletins")?.trigger("click");
      await wrapper.find("#post-text").setValue("Road closed");
      await wrapper.find("#pane-bulletins .bulletin-compose").trigger("submit");
      expect(socket.sent.filter((c) => (c as { cmd?: string }).cmd === "bulletin_post")).toEqual([{ cmd: "bulletin_post", slot: "BLN1", text: "Road closed" }]);
      expect(wrapper.find<HTMLInputElement>("#post-text").element.value).toBe("Road closed");
      socket.say({ type: "error", text: "bulletin_post: set your call first" });
      await flushPromises();
      expect(wrapper.find<HTMLInputElement>("#post-text").element.value).toBe("Road closed");
      socket.say({ type: "state", topic: "own_bulletins", rev: 0, value: { BLN1: ownBulletin("BLN1", { text: "Road closed" }) } });
      await flushPromises();
      expect(wrapper.find<HTMLInputElement>("#post-text").element.value).toBe("");
      const mine = wrapper.find("#pane-bulletins .bulletin.mine");
      expect(mine.find(".bulletin-head strong").text()).toBe("OH2GBA");
      expect(mine.find(".own-mark").text()).toBe("ours");
      expect(mine.find(".bulletin-text").text()).toBe("Road closed");
    });

    it("stops one of ours after two presses of its x, with one command, and the board forgets it when the daemon deletes it", async () => {
      const { wrapper, socket } = await open();
      socket.say({ type: "state", topic: "own_bulletins", rev: 0, value: { BLN1: ownBulletin("BLN1") } });
      await flushPromises();
      await tabButton(wrapper, "Bulletins")?.trigger("click");
      const x = () => wrapper.find("#pane-bulletins .mine .bulletin-delete");
      await x().trigger("click");
      await x().trigger("click");
      expect(socket.sent.filter((c) => (c as { cmd?: string }).cmd === "bulletin_unpost")).toEqual([{ cmd: "bulletin_unpost", slot: "BLN1" }]);
      expect(socket.sent.filter((c) => (c as { cmd?: string }).cmd === "bulletin_delete")).toEqual([]);
      socket.say({ type: "patch", topic: "own_bulletins", rev: 1, ops: [{ op: "del", key: "BLN1" }] });
      await flushPromises();
      expect(wrapper.find("#pane-bulletins .mine").exists()).toBe(false);
    });
  });

  describe("the Objects tab", () => {
    const mine = { LEADER: ownObject("LEADER", { comment: "Rescue 1" }) };
    const ours = {
      ...stations,
      LEADER: station("LEADER", {
        kind: "object",
        own: true,
        reported_by: "OH2GBA",
        lat: 60.3,
        lon: 25.0,
        symbol_name: "Car",
        distance_km: 15,
        bearing_deg: 10,
      }),
    };
    const sayObjects = async (socket: ReturnType<typeof FakeSocket.last>) => {
      socket.say({ type: "state", topic: "stations", rev: 1, value: ours });
      socket.say({ type: "state", topic: "own_objects", rev: 0, value: mine });
      await flushPromises();
    };
    const sent = (socket: ReturnType<typeof FakeSocket.last>, cmd: string) => socket.sent.filter((c) => (c as { cmd?: string }).cmd === cmd);
    const field = (wrapper: VueWrapper, label: string) =>
      wrapper
        .findAll("#pane-objects .field")
        .find((f) => f.find("label").text() === label)
        ?.find<HTMLInputElement>("input");
    const button = (wrapper: VueWrapper, text: string) => wrapper.findAll("#pane-objects button").find((b) => b.text() === text);

    it("comes after Bulletins and lists our objects", async () => {
      const { wrapper, socket } = await open();
      await sayObjects(socket);
      await tabButton(wrapper, "Objects")?.trigger("click");
      expect(wrapper.findAll("#pane-objects .ownobject")).toHaveLength(1);
      expect(wrapper.find("#pane-objects .ownobject strong").text()).toBe("LEADER");
    });

    it("makes an object from the form with one command, at the place we are unless a click on the map says another", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Objects")?.trigger("click");
      await wrapper.find("#pane-objects .toolbar .btn").trigger("click");
      expect(field(wrapper, "Latitude")?.element.value).toBe("60.17");
      await field(wrapper, "Name")?.setValue("MARK");
      await button(wrapper, "Pick on the map")?.trigger("click");
      FakeMap.last().fire("click", { lngLat: { lat: 60.5, lng: 25.5 } });
      await flushPromises();
      expect(field(wrapper, "Latitude")?.element.value).toBe("60.5");
      expect(field(wrapper, "Longitude")?.element.value).toBe("25.5");
      await wrapper.find("#pane-objects form").trigger("submit");
      expect(sent(socket, "object_set")).toEqual([
        {
          cmd: "object_set",
          name: "MARK",
          kind: "object",
          lat: 60.5,
          lon: 25.5,
          symbol_table: "/",
          symbol_code: ">",
          comment: "",
          course_deg: null,
          speed_kmh: null,
          path: null,
        },
      ]);
      expect(wrapper.find("#pane-objects .objform").exists()).toBe(true);
      expect(field(wrapper, "Name")?.element.value).toBe("MARK");
      socket.say({ type: "state", topic: "own_objects", rev: 0, value: { MARK: ownObject("MARK", { lat: 60.5, lon: 25.5 }) } });
      await flushPromises();
      expect(wrapper.find("#pane-objects .objform").exists()).toBe(false);
    });

    it("keeps the form and what was typed when the daemon refuses the object, and shows its error", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Objects")?.trigger("click");
      await wrapper.find("#pane-objects .toolbar .btn").trigger("click");
      await field(wrapper, "Name")?.setValue("MARK");
      await field(wrapper, "Comment")?.setValue("kept");
      await wrapper.find("#pane-objects form").trigger("submit");
      socket.say({ type: "error", text: "object_set: set your call first" });
      await flushPromises();
      expect(wrapper.find("#pane-objects .objform").exists()).toBe(true);
      expect(field(wrapper, "Comment")?.element.value).toBe("kept");
      expect(wrapper.find(".toast").text()).toContain("set your call first");
    });

    it("shows a pin on the map while the form has a place, and a click on the map is not the first-run guide's", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Objects")?.trigger("click");
      const pins = () => FakeMarker.live().filter((m) => m.element.classList.contains("setuppin"));
      expect(pins()).toHaveLength(0);
      await wrapper.find("#pane-objects .toolbar .btn").trigger("click");
      expect(pins()).toHaveLength(1);
      expect(pins()[0]?.lngLat).toEqual([24.94, 60.17]);
      await button(wrapper, "Cancel")?.trigger("click");
      expect(pins()).toHaveLength(0);
      expect(wrapper.find(".setup").exists()).toBe(false);
      expect(sent(socket, "set_config")).toEqual([]);
    });

    it("kills an object after two presses of its x, with one command", async () => {
      const { wrapper, socket } = await open();
      await sayObjects(socket);
      await tabButton(wrapper, "Objects")?.trigger("click");
      const x = () => wrapper.find("#pane-objects .ownobject .bulletin-delete");
      await x().trigger("click");
      expect(sent(socket, "object_kill")).toEqual([]);
      await x().trigger("click");
      expect(sent(socket, "object_kill")).toEqual([{ cmd: "object_kill", name: "LEADER" }]);
    });

    it("changes an object from its card on the map: Edit opens the Objects tab with it, and Save sends the change", async () => {
      const { wrapper, socket } = await open();
      await sayObjects(socket);
      const marker = FakeMarker.live().find((m) => m.element.textContent === "LEADER");
      expect(marker?.draggable).toBe(true);
      marker?.element.click();
      await flushPromises();
      expect(wrapper.find(".card .card-call").text()).toContain("LEADER");
      await wrapper.find(".card .card-foot .primary").trigger("click");
      expect(tabButton(wrapper, "Objects")?.attributes("aria-selected")).toBe("true");
      expect(wrapper.find<HTMLInputElement>("#pane-objects .objform input[maxlength='9']").element.value).toBe("LEADER");
      await field(wrapper, "Comment")?.setValue("Moved on");
      await wrapper.find("#pane-objects form").trigger("submit");
      expect(sent(socket, "object_set")).toMatchObject([{ name: "LEADER", comment: "Moved on", lat: 60.2, lon: 24.9 }]);
    });

    it("kills an object from its card, which asks twice", async () => {
      const { wrapper, socket } = await open();
      await sayObjects(socket);
      FakeMarker.live()
        .find((m) => m.element.textContent === "LEADER")
        ?.element.click();
      await flushPromises();
      const kill = () => wrapper.find(".card .card-foot .forget");
      await kill().trigger("click");
      expect(kill().text()).toBe("Really kill?");
      await kill().trigger("click");
      expect(sent(socket, "object_kill")).toEqual([{ cmd: "object_kill", name: "LEADER" }]);
      expect(sent(socket, "forget_station")).toEqual([]);
    });

    it("moves an object where its marker is dropped, with one command that keeps the rest of it", async () => {
      const { socket } = await open();
      await sayObjects(socket);
      FakeMarker.live()
        .find((m) => m.element.textContent === "LEADER")
        ?.dragTo(60.8, 25.9);
      await flushPromises();
      expect(sent(socket, "object_set")).toEqual([
        {
          cmd: "object_set",
          name: "LEADER",
          kind: "object",
          lat: 60.8,
          lon: 25.9,
          symbol_table: "/",
          symbol_code: ">",
          comment: "Rescue 1",
          course_deg: null,
          speed_kmh: null,
          path: null,
        },
      ]);
    });

    it("lets the first-run guide have the click of the map while it picks a position", async () => {
      const { wrapper, socket } = await open();
      socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ "station/call": "" }) });
      await flushPromises();
      await wrapper.find("#setup-call").setValue("oh2abc");
      await wrapper.find(".setup form").trigger("submit");
      expect(wrapper.find("#setup-lat").exists()).toBe(true);
      await tabButton(wrapper, "Objects")?.trigger("click");
      await wrapper.find("#pane-objects .toolbar .btn").trigger("click");
      await button(wrapper, "Pick on the map")?.trigger("click");
      FakeMap.last().fire("click", { lngLat: { lat: 59.5, lng: 24.5 } });
      await flushPromises();
      expect(wrapper.find<HTMLInputElement>("#setup-lat").element.value).toBe("59.5");
      expect(field(wrapper, "Latitude")?.element.value).toBe("60.17");
    });
  });

  describe("a conversation", () => {
    const conv = (wrapper: VueWrapper, call: string) => wrapper.findAll("#pane-messages .conv").find((c) => c.find(".conv-call").text() === call);
    const x = (wrapper: VueWrapper, call: string) =>
      wrapper
        .findAll("#pane-messages .conv-item")
        .find((c) => c.find(".conv-call").text() === call)
        ?.find(".conv-delete");

    it("is opened by a click on its row, and another row opens that one; the open one is the highlighted row, and a click on it keeps it open", async () => {
      const { wrapper } = await open();
      await tabButton(wrapper, "Messages")?.trigger("click");
      expect(wrapper.find("#pane-messages .conv.active").exists()).toBe(false);
      expect(wrapper.find("#pane-messages .convo-empty").text()).toContain("Choose a conversation");
      await conv(wrapper, "OH2RDG")?.trigger("click");
      expect(wrapper.findAll("#pane-messages .bubble")).toHaveLength(2);
      expect(wrapper.find("#pane-messages .convo-title").text()).toBe("OH2RDG");
      await conv(wrapper, "OH2PU-9")?.trigger("click");
      expect(wrapper.find("#pane-messages .conv.active .conv-call").text()).toBe("OH2PU-9");
      expect(wrapper.find("#pane-messages .convo-title").text()).toBe("OH2PU-9");
      await conv(wrapper, "OH2PU-9")?.trigger("click");
      expect(wrapper.find("#pane-messages .conv.active .conv-call").text()).toBe("OH2PU-9");
      expect(wrapper.findAll("#pane-messages .conv")).toHaveLength(2);
    });

    it("is opened by the Message button of the station's card, again and again, also for a station with no conversation yet, which it creates", async () => {
      const { wrapper, socket } = await open();
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
      expect(wrapper.find("#pane-messages .new-message").exists()).toBe(false);
      expect(wrapper.find("#msg-to").exists()).toBe(false);
      await wrapper
        .findAll("#pane-stations tbody tr")
        .find((r) => r.text().includes("OH2NOPOS"))
        ?.trigger("click");
      await message()?.trigger("click");
      expect(wrapper.find("#pane-messages .convo-title").text()).toBe("OH2NOPOS");
      expect(wrapper.find("#pane-messages .bubbles").text()).toContain("No message with OH2NOPOS yet");
      await wrapper.find("#msg-text").setValue("Moi");
      await wrapper.find("#pane-messages form").trigger("submit");
      expect(socket.sent).toContainEqual({ cmd: "send_message", to: "OH2NOPOS", text: "Moi" });
    });

    it("is opened straight, without the list, by the Message button of the station's card on a narrow panel, and Esc is back to the list", async () => {
      panelWidth.set(400);
      const { wrapper } = await open();
      await wrapper
        .findAll("#pane-stations tbody tr")
        .find((r) => r.text().includes("OH2PU-9"))
        ?.trigger("click");
      await wrapper
        .findAll(".card .btn")
        .find((b) => b.text() === "Message")
        ?.trigger("click");
      expect(wrapper.find("#pane-messages .convlist").exists()).toBe(false);
      expect(wrapper.find("#pane-messages .convo-title").text()).toBe("OH2PU-9");
      expect(wrapper.find("#msg-to").exists()).toBe(false);
      await wrapper.find("#pane-messages .convo").trigger("keydown", { key: "Escape" });
      expect(wrapper.find("#pane-messages .convo").exists()).toBe(false);
      expect(wrapper.findAll("#pane-messages .conv")).toHaveLength(2);
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
      expect(wrapper.find("#pane-messages .convo").exists()).toBe(false);
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
      await wrapper.find<HTMLInputElement>("#pane-messages .convlist-overheard input").setValue(true);
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

    it("sends mail as a message to EMAIL-2 and a new contact and the commands as their texts, and keeps the addressee in the list", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Email")?.trigger("click");
      const pane = () => wrapper.find("#pane-email");
      const button = (label: string) =>
        pane()
          .findAll("button")
          .find((b) => b.text() === label);
      await button("New email")?.trigger("click");
      await wrapper.find("#mail-to").setValue("jane@example.com");
      await wrapper.find("#mail-text").setValue("Hello");
      await wrapper.find("#pane-email form.mailform").trigger("submit");
      expect(socket.sent).toContainEqual({ cmd: "send_message", to: "EMAIL-2", text: "jane@example.com Hello" });
      expect(JSON.stringify(socket.sent)).not.toContain("_attempts");
      expect(pane().find("form.mailform").exists()).toBe(false);
      expect(JSON.parse(localStorage.getItem("NeoAPRS.emailto") ?? "[]")).toEqual(["jane@example.com"]);
      await button("Contacts")?.trigger("click");
      await wrapper.find("#contact-name").setValue("me");
      await wrapper.find("#contact-address").setValue("jane@example.com");
      await wrapper.find("#pane-email form[aria-label='Add contact']").trigger("submit");
      // the gateway's messages come back as rows of the topic: the contact is listed from the one we sent
      await say(socket, 1, message(10, { to_call: "EMAIL-2", text: "me jane@example.com", state: "acked" }));
      await button("Email me the list")?.trigger("click");
      await button("Remove")?.trigger("click");
      await button("sure?")?.trigger("click");
      await button("Check for mail")?.trigger("click");
      expect(socket.sent.slice(-4)).toEqual([
        { cmd: "send_message", to: "EMAIL-2", text: "me jane@example.com" },
        { cmd: "send_message", to: "EMAIL-2", text: "me L" },
        { cmd: "send_message", to: "EMAIL-2", text: "me R" },
        { cmd: "send_message", to: "EMAIL-2", text: "get" },
      ]);
    });

    it("deletes a row of the list on the daemon after a second press", async () => {
      const { wrapper, socket } = await open();
      await say(socket, 1, message(10, { to_call: "EMAIL-2", text: "me hello" }));
      await tabButton(wrapper, "Email")?.trigger("click");
      await wrapper.find("#pane-email .mail-delete").trigger("click");
      expect(JSON.stringify(socket.sent)).not.toContain("message_delete");
      await wrapper.find("#pane-email .mail-delete").trigger("click");
      expect(socket.sent).toContainEqual({ cmd: "message_delete", id: 10 });
    });

    it("has no attempts field in the Email tab or in the Messages header: the daemon decides", async () => {
      const { wrapper } = await open();
      await tabButton(wrapper, "Email")?.trigger("click");
      expect(wrapper.find("#pane-email .attempts-input").exists()).toBe(false);
      expect(wrapper.find("#pane-messages .attempts-input").exists()).toBe(false);
      expect(wrapper.find("#pane-email").text()).not.toContain("Attempts");
    });

    it("shows the thread with the gateway there and leaves it out of the Messages tab and its count", async () => {
      const { wrapper, socket } = await open();
      await say(socket, 1, message(10, { to_call: "EMAIL-2", text: "me hello" }), gateway(11));
      expect(wrapper.findAll("#pane-email .mail").map((m) => m.find(".mail-title").text())).toEqual(["To me", "From EMAIL-2"]);
      expect(wrapper.findAll("#pane-messages .conv-call").map((c) => c.text())).toEqual(["OH2PU-9", "OH2RDG"]);
      expect(tabButton(wrapper, "Messages")?.find(".badge").text()).toBe("2");
      expect(wrapper.find(".headmail").text()).toContain("3"); // the messages not seen, the gateway's one included: the count of the title and of the folded panel's handle too
    });

    it("shows what came in while the tab was away in bold until the tab is left again", async () => {
      const { wrapper, socket } = await open();
      await say(socket, 1, gateway(11));
      await tabButton(wrapper, "Email")?.trigger("click");
      expect(wrapper.find("#pane-email .mail").classes()).toContain("fresh");
      await say(socket, 2, gateway(12));
      expect(wrapper.findAll("#pane-email .mail.fresh")).toHaveLength(2);
      await tabButton(wrapper, "Stations")?.trigger("click");
      await tabButton(wrapper, "Email")?.trigger("click");
      expect(wrapper.findAll("#pane-email .mail.fresh")).toHaveLength(0);
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

    it("has one count of the messages not seen: the header, the folded handle and the title say the same", async () => {
      const { wrapper, socket } = await open();
      await say(socket, 1, gateway(11), gateway(12));
      expect(wrapper.find(".headmail").text()).toContain("4");
      expect(document.title).toBe("(4) NeoAPRS");
      await wrapper.find(".panel-fold").trigger("click");
      expect(wrapper.find(".fold-badge").text()).toBe("4");
      expect(wrapper.find(".fold-badge").attributes("title")).toBe("4 messages not seen yet");
    });

    it("opens the Email tab from the header when the messages not seen are all the gateway's", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Messages")?.trigger("click");
      for (const conv of wrapper.findAll("#pane-messages .conv")) await conv.trigger("click");
      await say(socket, 1, gateway(11));
      expect(wrapper.find(".headmail").text()).toContain("1");
      await tabButton(wrapper, "Packets")?.trigger("click");
      await wrapper.find(".headmail").trigger("click");
      expect(wrapper.find("[aria-selected='true']").text()).toContain("Email");
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
    await tabButton(wrapper, "Settings")?.trigger("click");
    expect(wrapper.find("[aria-selected='true']").text()).toBe("Settings");
    vi.restoreAllMocks();
  });

  it("downloads the map from the Settings tab: the buttons send the commands and the progress follows the topic", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "map", rev: 0, value: mapState() });
    await flushPromises();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const button = () => wrapper.find("#pane-settings .mapfetch-actions button.primary");
    await button().trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "map_estimate" });
    expect(socket.sent).not.toContainEqual({ cmd: "map_fetch" });
    expect(button().text()).toBe("Checking size…");
    socket.say({
      type: "patch",
      topic: "map",
      rev: 1,
      ops: [
        {
          op: "replace",
          value: mapState({ estimate: { bytes: 493_000_000, tiles: 41233, radius_km: 150, maxzoom: 12, box: [22.1, 58.8, 27.8, 61.5], build: "20261022" } }),
        },
      ],
    });
    await flushPromises();
    expect(button().text()).toBe("Download 493 MB?");
    await button().trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "map_fetch" });
    socket.say({
      type: "patch",
      topic: "map",
      rev: 2,
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

describe("the alert of this browser", () => {
  const patch = (socket: FakeSocket, rev: number, key: string, row: object) =>
    socket.say({ type: "patch", topic: "messages", rev, ops: [{ op: "set", key, value: row }] });

  it("has one Notifications group in the Settings tab: the daemon's own alert, then the choice of this browser with its two tests", async () => {
    stubBrowser();
    const { wrapper } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const groups = wrapper.findAll("#pane-settings fieldset").filter((g) => g.find("legend").text() === "Notifications");
    expect(groups).toHaveLength(1);
    expect(groups[0]?.findAll("h3").map((h) => h.text().replace(/ i$/, ""))).toEqual(["On the NeoAPRS computer", "In this browser"]);
    expect(groups[0]?.findAll("label").map((l) => l.text())).toEqual(["Alert", "Command", "Alert for a new message", "Sound", "Pop-up"]);
    expect(groups[0]?.findAll("button:not(.info-toggle)").map((b) => b.text())).toEqual(["Test", "Test sound", "Test pop-up"]);
  });

  it("is off on the loopback: a message to us makes no sound there", async () => {
    stubBrowser();
    const { socket } = await open();
    patch(socket, 1, "4", incoming(4, "OH2DPN"));
    await flushPromises();
    expect(FakeAudioContext.played()).toBe(0);
    expect(FakeNotification.shown).toEqual([]);
  });

  it("chimes once for a message to us that arrives after the page loaded, flashes the tab, and not again on a reconnect", async () => {
    stubBrowser({ secure: false });
    openedAt("192.168.1.20");
    setSeen(false);
    const { socket } = await open();
    window.dispatchEvent(new Event("pointerdown"));
    await flushPromises();
    patch(socket, 1, "4", incoming(4, "OH2DPN", { text: "Moi!" }));
    await flushPromises();
    expect(FakeAudioContext.played()).toBe(2);
    expect(document.title).toBe("✉ OH2DPN");
    patch(socket, 2, "5", incoming(5, "OH2RDG", { state: "overheard", to_call: "OH2XYZ" }));
    patch(socket, 3, "6", message(6, { to_call: "OH2RDG" }));
    await flushPromises();
    expect(FakeAudioContext.played()).toBe(2);
    socket.hangUp();
    vi.useFakeTimers();
    vi.advanceTimersByTime(1000);
    vi.useRealTimers();
    const again = FakeSocket.last();
    again.say(hello());
    again.say({ type: "state", topic: "messages", rev: 0, value: { ...messages, "4": incoming(4, "OH2DPN", { text: "Moi!" }) } });
    await flushPromises();
    expect(FakeAudioContext.played()).toBe(2);
  });

  it("shows a notification that opens the conversation when it is clicked", async () => {
    stubBrowser();
    FakeNotification.permission = "granted";
    openedAt("192.168.1.20");
    vi.spyOn(window, "focus").mockImplementation(() => undefined);
    const { wrapper, socket } = await open();
    patch(socket, 1, "4", incoming(4, "OH2DPN", { text: "Moi!" }));
    await flushPromises();
    expect(FakeNotification.shown.map((n) => n.title)).toEqual(["APRS message from OH2DPN"]);
    FakeNotification.shown[0]?.onclick?.();
    await flushPromises();
    expect(tabButton(wrapper, "Messages")?.attributes("aria-selected")).toBe("true");
    expect(wrapper.find("#pane-messages").text()).toContain("Moi!");
  });

  it("opens the steps of the update for the way this copy was installed from the new version under the panel, and closes them when it is gone", async () => {
    const { wrapper, socket } = await open();
    expect(wrapper.find(".updatepanel").exists()).toBe(false);
    socket.say(hello({ install: { kind: "uv-tool", appimage: "", service: true, arch: "" } }));
    socket.say(status({ update: { version: "0.4.0", url: "", message: "" } }));
    await flushPromises();
    await wrapper.find("button.update").trigger("click");
    const panel = wrapper.find(".updatepanel");
    expect(panel.find("h2").text()).toBe("Update to 0.4.0");
    expect(panel.find("code").text()).toContain("install.sh | sh");
    socket.say(status());
    await flushPromises();
    expect(wrapper.find(".updatepanel").exists()).toBe(false);
  });

  it("asks the daemon to check at once from the Settings tab and opens the steps from the answer", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const button = wrapper.findAll("#pane-settings button").find((b) => b.text() === "Check now");
    await button?.trigger("click");
    expect(socket.sent.filter((c) => (c as { cmd: string }).cmd === "update_check")).toHaveLength(1);
    socket.say({ type: "update_result", outcome: "newer", version: "0.4.0", text: "" });
    socket.say(status({ update: { version: "0.4.0", url: "", message: "" } }));
    await flushPromises();
    expect(wrapper.find("button.update").text()).toBe("Update to 0.4.0");
    await wrapper.find("#pane-settings button.updatecheck-result").trigger("click");
    expect(wrapper.find(".updatepanel h2").text()).toBe("Update to 0.4.0");
  });
});
