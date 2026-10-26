import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent } from "vue";
import { socketUrl, useDaemon } from "@/composables/useDaemon";
import { FakeFetch } from "@/test/fakefetch";
import { FakeSocket } from "@/test/fakesocket";
import { PAGE_VERSION } from "@/lib/build";
import { pageErrors } from "@/lib/pageerrors";
import { bulletin, configValues, errorOf, gpsState, hello, message, ownBulletin, ownObject, packet, station, tncState } from "@/test/fixtures";

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

describe("useDaemon and the errors of the page", () => {
  it("sends an error of the page as page_error once the connection is open, and holds it until then", () => {
    const { socket, wrapper } = setUp();
    pageErrors.record(new Error("before the daemon spoke"), "window");
    expect(socket.sent).toEqual([]);
    socket.say(hello());
    expect(socket.sent).toEqual([expect.objectContaining({ cmd: "page_error", message: "before the daemon spoke", source: "window" })]);
    pageErrors.record(new Error("after"), "window");
    expect(socket.sent).toHaveLength(2);
    wrapper.unmount();
    pageErrors.record(new Error("after the page is gone"), "window");
    expect(socket.sent).toHaveLength(2);
  });
});

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
    socket.say(hello());
    socket.say({ type: "state", topic: "stations", rev: 0, value: { A: station("A") } });
    socket.say({ type: "state", topic: "packets", rev: 0, value: { "1": packet(1) } });
    socket.say({ type: "state", topic: "tnc", rev: 0, value: tncState() });
    socket.say({ type: "state", topic: "config", rev: 0, value: configValues() });
    socket.say({ type: "state", topic: "gps", rev: 0, value: gpsState({ mobile: true }) });
    socket.say({ type: "state", topic: "messages", rev: 0, value: { "1": message(1) } });
    socket.say({ type: "state", topic: "station_prefs", rev: 0, value: { OH2RDG: { path: "WIDE2-1" } } });
    socket.say({ type: "state", topic: "bulletins", rev: 0, value: { "OH2XYZ/BLN1": bulletin("BLN1") } });
    expect(daemon.connection.value).toBe("open");
    expect(daemon.bulletins.get("OH2XYZ/BLN1")?.text).toBe("text of BLN1");
    expect(daemon.messages.get("1")?.text).toBe("message 1");
    expect(daemon.stationPrefs.get("OH2RDG")).toEqual({ path: "WIDE2-1" });
    expect(daemon.version.value).toBe(PAGE_VERSION);
    expect(daemon.install.value).toEqual({ kind: "pip", appimage: "", service: false, arch: "" });
    expect([...daemon.stations.keys()]).toEqual(["A"]);
    expect(daemon.packets.get("1")?.id).toBe(1);
    expect(daemon.tnc.value?.state).toBe("connected");
    expect(daemon.config.value?.values["station/call"]).toBe("OH2GBA");
    expect(daemon.gps.value).toEqual(gpsState({ mobile: true }));
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

  it("holds our own objects by name and our own bulletins by slot, whole and by patch", () => {
    const { daemon, socket } = setUp();
    socket.say(hello());
    socket.say({ type: "state", topic: "own_objects", rev: 0, value: { LEADER: ownObject("LEADER"), AID: ownObject("AID", { kind: "item" }) } });
    socket.say({ type: "state", topic: "own_bulletins", rev: 0, value: { BLN1: ownBulletin("BLN1") } });
    expect([...daemon.ownObjects.keys()]).toEqual(["LEADER", "AID"]);
    expect(daemon.ownBulletins.get("BLN1")?.text).toBe("ours in BLN1");
    socket.say({
      type: "patch",
      topic: "own_objects",
      rev: 1,
      ops: [
        { op: "set", key: "LEADER", value: ownObject("LEADER", { sent: 5 }) },
        { op: "del", key: "AID" },
      ],
    });
    socket.say({ type: "patch", topic: "own_bulletins", rev: 1, ops: [{ op: "del", key: "BLN1" }] });
    expect([...daemon.ownObjects.keys()]).toEqual(["LEADER"]);
    expect(daemon.ownObjects.get("LEADER")?.sent).toBe(5);
    expect(daemon.ownBulletins.size).toBe(0);
    expect(daemon.config.value).toBeNull();
  });

  it("keeps the latest answer to weather_series of each station", () => {
    const { daemon, socket } = setUp();
    expect(daemon.weatherSeriesByCall.value.size).toBe(0);
    socket.say({ type: "weather_series", call: "OH2MUI", hours: 24, points: [] });
    socket.say({ type: "weather_series", call: "OH2NJR", hours: 168, points: [["2026-10-21T12:00:00Z", 10, null, null, null, null, null]] });
    expect([...daemon.weatherSeriesByCall.value.keys()]).toEqual(["OH2MUI", "OH2NJR"]);
    expect(daemon.weatherSeriesByCall.value.get("OH2NJR")?.points).toHaveLength(1);
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
    socket.say(errorOf("nope"));
    socket.say(errorOf("nope"));
    expect(daemon.lastError.value).toEqual({ cmd: "", key: null, code: "other", params: {}, text: "nope", n: 2 });
    socket.say(errorOf("set_config: station/lat: 95 is out", "setting.range", { value: 95 }));
    expect(daemon.lastError.value).toMatchObject({ cmd: "set_config", key: "station/lat", code: "setting.range", params: { value: 95 }, n: 3 });
  });

  it("sends a command, and says so in the toast when it cannot", () => {
    const { daemon, socket } = setUp();
    expect(daemon.send({ cmd: "ping" })).toBe(false);
    expect(daemon.lastError.value).toMatchObject({ cmd: "", key: null, code: "not_connected", text: "Not connected to the daemon." });
    socket.say(hello());
    expect(daemon.send({ cmd: "tnc_reconnect" })).toBe(true);
    expect(socket.sent).toEqual([{ cmd: "tnc_reconnect" }]);
  });

  it("shows the connection as closed when the socket drops", () => {
    const { daemon, socket } = setUp();
    socket.say(hello());
    socket.hangUp();
    expect(daemon.connection.value).toBe("closed");
  });

  it("loads the page again, to show the key screen, when a socket that never spoke was refused for want of a login", async () => {
    const reload = vi.spyOn(location, "reload").mockImplementation(() => undefined);
    const daemon = new FakeFetch(401);
    vi.stubGlobal("fetch", daemon.fetch);
    const { socket } = setUp();
    socket.hangUp();
    await vi.waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
    expect(daemon.calls.map((c) => c.url)).toEqual(["http://127.0.0.1:7303/access"]);
    reload.mockRestore();
  });

  it("does not load the page again when the daemon is only not there", async () => {
    const reload = vi.spyOn(location, "reload").mockImplementation(() => undefined);
    const { socket } = setUp();
    socket.hangUp();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(reload).not.toHaveBeenCalled();
    reload.mockRestore();
  });

  it("loads the page again when the daemon it meets is of another version, once, and again for a later update after a match", () => {
    const reload = vi.spyOn(location, "reload").mockImplementation(() => undefined);
    sessionStorage.clear();
    const { socket } = setUp();
    socket.say(hello({ version: "99.0.0" }));
    socket.say(hello({ version: "99.0.0" }));
    expect(reload).toHaveBeenCalledTimes(1);
    socket.say(hello());
    expect(reload).toHaveBeenCalledTimes(1);
    socket.say(hello({ version: "99.0.0" }));
    expect(reload).toHaveBeenCalledTimes(2);
    sessionStorage.clear();
    reload.mockRestore();
  });

  it("does not load the page again for a daemon of its own version", () => {
    const reload = vi.spyOn(location, "reload").mockImplementation(() => undefined);
    const { socket } = setUp();
    socket.say(hello());
    expect(reload).not.toHaveBeenCalled();
    reload.mockRestore();
  });

  it("keeps the latest answer to update_check", () => {
    const { daemon, socket } = setUp();
    expect(daemon.updateResult.value).toBeNull();
    socket.say({ type: "update_result", outcome: "current", version: "0.3.0", text: "" });
    expect(daemon.updateResult.value).toEqual({ type: "update_result", outcome: "current", version: "0.3.0", text: "" });
  });

  it("finds the socket beside the page", () => {
    expect(socketUrl()).toBe("ws://127.0.0.1:7303/ws");
  });
});
