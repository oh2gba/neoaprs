// The page mounted as the tests of App.*.test.ts need it: the daemon's state as a socket tells it, the way to the tab buttons, and the page's globals (a desktop window, the clock at the fixtures' time, no storage) put in place and taken away around each test.
import "@/test/mockmap";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, vi } from "vitest";
import App from "@/App.vue";
import { resetFakes } from "@/test/fakemap";
import { FakeSocket } from "@/test/fakesocket";
import { stubWidth } from "@/test/width";
import { openedAt } from "@/test/fakealert";
import { ago, configValues, hello, incoming, message, NOW, packet, station, status, tncState } from "@/test/fixtures";

export const stations = {
  OH2GBA: station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94, symbol_table: "", symbol_code: "", distance_km: null, bearing_deg: null }),
  "OH2PU-9": station("OH2PU-9", { lat: 60.2, lon: 24.65, distance_km: 16, bearing_deg: 282, last_heard: ago(30) }),
  OH2RDG: station("OH2RDG", { symbol_table: "N", symbol_code: "#", lat: 60.12, lon: 24.49, last_heard: ago(10) }),
  OH2NOPOS: station("OH2NOPOS", { lat: null, lon: null, last_heard: ago(90) }),
};

export const messages = {
  "1": message(1, { to_call: "OH2RDG", text: "Hello Pekka", state: "acked", attempts: 1, at: ago(500) }),
  "2": incoming(2, "OH2RDG", { text: "Moi!", at: ago(400) }),
  "3": incoming(3, "OH2PU-9", { text: "Are you there?", at: ago(300) }),
};

/** The page, mounted on the document. */
export function mountApp() {
  return mount(App, { attachTo: document.body });
}

/** The page mounted, and the daemon's first words told over the fake socket: the four stations, two packets, the radio, the settings, three messages, a path for one station and the status. */
export async function open() {
  const wrapper = mountApp();
  await flushPromises();
  const socket = FakeSocket.last();
  socket.say(hello());
  socket.say({ type: "state", topic: "stations", rev: 0, value: stations });
  socket.say({ type: "state", topic: "packets", rev: 0, value: { "1": packet(1), "2": packet(2, { summary: "second" }) } });
  socket.say({ type: "state", topic: "tnc", rev: 0, value: tncState() });
  socket.say({ type: "state", topic: "config", rev: 0, value: configValues() }); // (the clock stands at the fixtures' time, so nothing times out)
  socket.say({ type: "state", topic: "messages", rev: 0, value: messages });
  socket.say({ type: "state", topic: "station_prefs", rev: 0, value: { OH2RDG: { path: "OH2RCH-2", rf_only: false } } });
  socket.say(status());
  await flushPromises();
  return { wrapper, socket };
}

export const tabButton = (wrapper: VueWrapper, title: string) => wrapper.findAll("[role='tab']").find((t) => t.text().startsWith(title));

/** Around each test of the file that calls it: the panel 720 px wide (the Messages tab has the list beside the conversation; the narrow layout is tried where a test says so), a desktop window, the fake socket, and the clock at the fixtures' time. */
export function useAppHarness(): { setPanelWidth: (px: number) => void } {
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
  return { setPanelWidth: (px) => panelWidth.set(px) };
}
