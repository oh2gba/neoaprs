import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent } from "vue";
import { socketUrl, useDaemon } from "@/composables/useDaemon";
import { PROTOCOL } from "@/protocol/lists";
import { FakeSocket } from "@/test/fakesocket";
import { bulletin, configValues, message, packet, station, tncState } from "@/test/fixtures";

function setUp() {
  let daemon: ReturnType<typeof useDaemon> | undefined;
  const wrapper = mount(
    defineComponent({
      setup() {
        daemon = useDaemon(() => "ws://host/ws");
        return () => null;
      },
    }),
  );
  if (!daemon) throw new Error("not set up");
  return { daemon, wrapper, socket: FakeSocket.last() };
}

beforeEach(() => {
  FakeSocket.all = [];
  vi.stubGlobal("WebSocket", FakeSocket);
});
afterEach(() => vi.unstubAllGlobals());

describe("useDaemon", () => {
  it("opens the socket when mounted and closes it when unmounted", () => {
    const { wrapper, socket, daemon } = setUp();
    expect(socket.url).toBe("ws://host/ws");
    expect(daemon.connection.value).toBe("connecting");
    wrapper.unmount();
    expect(socket.closed).toBe(true);
    expect(daemon.connection.value).toBe("closed");
  });

  it("holds the topics as reactive state", () => {
    const { daemon, socket } = setUp();
    socket.say({ type: "hello", protocol: PROTOCOL, version: "0.1.0", topics: [] });
    socket.say({ type: "state", topic: "stations", rev: 0, value: { A: station("A") } });
    socket.say({ type: "state", topic: "packets", rev: 0, value: { "1": packet(1) } });
    socket.say({ type: "state", topic: "tnc", rev: 0, value: tncState() });
    socket.say({ type: "state", topic: "config", rev: 0, value: configValues() });
    socket.say({ type: "state", topic: "messages", rev: 0, value: { "1": message(1) } });
    socket.say({ type: "state", topic: "station_prefs", rev: 0, value: { OH2RDG: { path: "WIDE2-1", hide_after_min: 45 } } });
    socket.say({ type: "state", topic: "bulletins", rev: 0, value: { "OH2XYZ/BLN1": bulletin("BLN1") } });
    expect(daemon.connection.value).toBe("open");
    expect(daemon.bulletins.get("OH2XYZ/BLN1")?.text).toBe("text of BLN1");
    expect(daemon.messages.get("1")?.text).toBe("message 1");
    expect(daemon.stationPrefs.get("OH2RDG")).toEqual({ path: "WIDE2-1", hide_after_min: 45 });
    expect(daemon.version.value).toBe("0.1.0");
    expect([...daemon.stations.keys()]).toEqual(["A"]);
    expect(daemon.packets.get("1")?.id).toBe(1);
    expect(daemon.tnc.value?.state).toBe("connected");
    expect(daemon.config.value?.values["station/call"]).toBe("OH2GBA");
    socket.say({
      type: "patch",
      topic: "stations",
      rev: 1,
      ops: [
        { op: "set", key: "B", value: station("B") },
        { op: "del", key: "A" },
      ],
    });
    expect([...daemon.stations.keys()]).toEqual(["B"]);
  });

  it("keeps the latest answer to weather_series", () => {
    const { daemon, socket } = setUp();
    expect(daemon.weatherSeries.value).toBeNull();
    socket.say({ type: "weather_series", call: "OH2MUI", hours: 24, points: [] });
    socket.say({ type: "weather_series", call: "OH2NJR", hours: 168, points: [["2026-10-21T12:00:00Z", 10, null, null, null, null, null]] });
    expect(daemon.weatherSeries.value?.call).toBe("OH2NJR");
    expect(daemon.weatherSeries.value?.points).toHaveLength(1);
  });

  it("keeps the latest answer to alert_test", () => {
    const { daemon, socket } = setUp();
    expect(daemon.alertResult.value).toBeNull();
    socket.say({ type: "alert_result", ok: true, text: "ran" });
    socket.say({ type: "alert_result", ok: true, text: "ran" });
    expect(daemon.alertResult.value).toEqual({ type: "alert_result", ok: true, text: "ran" });
  });

  it("keeps the latest answer to list_ports", () => {
    const { daemon, socket } = setUp();
    expect(daemon.ports.value).toBeNull();
    socket.say({ type: "ports", ports: [], search: false });
    socket.say({ type: "ports", ports: [{ device: "COM3", description: "USB Serial Port (COM3)", hwid: "n/a", vid: null, pid: null }], search: false });
    expect(daemon.ports.value?.ports.map((p) => p.device)).toEqual(["COM3"]);
  });

  it("keeps the status and the last error", () => {
    const { daemon, socket } = setUp();
    socket.say({ type: "status", version: "0.1.0", started_at: "2026-10-21T00:00:00Z", packets: 5, stations: 2, call: "OH2GBA", lat: 60, lon: 24 });
    expect(daemon.status.value?.packets).toBe(5);
    socket.say({ type: "error", text: "nope" });
    socket.say({ type: "error", text: "nope" });
    expect(daemon.lastError.value).toEqual({ text: "nope", n: 2 });
  });

  it("sends a command, and says so in the toast when it cannot", () => {
    const { daemon, socket } = setUp();
    expect(daemon.send({ cmd: "ping" })).toBe(false);
    expect(daemon.lastError.value?.text).toBe("Not connected to the daemon.");
    socket.say({ type: "hello", protocol: PROTOCOL, version: "0.1.0", topics: [] });
    expect(daemon.send({ cmd: "tnc_reconnect" })).toBe(true);
    expect(socket.sent).toEqual([{ cmd: "tnc_reconnect" }]);
  });

  it("shows the connection as closed when the socket drops", () => {
    const { daemon, socket } = setUp();
    socket.say({ type: "hello", protocol: PROTOCOL, version: "0.1.0", topics: [] });
    socket.hangUp();
    expect(daemon.connection.value).toBe("closed");
  });

  it("finds the socket beside the page", () => {
    expect(socketUrl()).toBe("ws://127.0.0.1:7303/ws");
  });
});
