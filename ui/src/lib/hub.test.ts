import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FIRST_DELAY_MS, Hub, MAX_DELAY_MS, nextDelay, parseMessage, type Connection, type Store } from "@/lib/hub";
import { PROTOCOL } from "@/protocol/lists";
import type {
  AlertResultMessage,
  ErrorMessage,
  GpsState,
  IgateState,
  HelloMessage,
  BulletinRow,
  MessageRow,
  OwnBulletinRow,
  OwnObjectRow,
  PacketRow,
  PortsMessage,
  RadioSearchMessage,
  StationPref,
  StationRow,
  TncState,
  UpdateResultMessage,
  WeatherSeriesMessage,
} from "@/protocol/protocol";
import { FakeSocket } from "@/test/fakesocket";
import {
  bulletin,
  configValues,
  errorOf,
  gpsState,
  igateState,
  hello,
  mapFile,
  mapState,
  message,
  ownBulletin,
  ownObject,
  packet,
  station,
  tncState,
} from "@/test/fixtures";

function memory() {
  const seen = {
    connection: [] as Connection[],
    errors: [] as ErrorMessage[],
    series: [] as WeatherSeriesMessage[],
    alerts: [] as AlertResultMessage[],
    ports: [] as PortsMessage[],
    searches: [] as RadioSearchMessage[],
    updates: [] as UpdateResultMessage[],
    stations: new Map<string, StationRow>(),
    packets: new Map<string, PacketRow>(),
    messages: new Map<string, MessageRow>(),
    bulletins: new Map<string, BulletinRow>(),
    prefs: new Map<string, StationPref>(),
    ownObjects: new Map<string, OwnObjectRow>(),
    ownBulletins: new Map<string, OwnBulletinRow>(),
    tnc: null as TncState | null,
    config: null as unknown,
    map: null as unknown,
    update: null as unknown,
    gps: null as unknown,
    igate: null as unknown,
    hello: 0,
    statuses: 0,
    stale: 0,
  };
  const store: Store = {
    connection: (c) => seen.connection.push(c),
    hello: () => seen.hello++,
    status: () => seen.statuses++,
    error: (e) => seen.errors.push(e),
    weatherSeries: (m) => seen.series.push(m),
    alertResult: (m) => seen.alerts.push(m),
    ports: (m) => seen.ports.push(m),
    radioSearch: (m) => seen.searches.push(m),
    updateResult: (m) => seen.updates.push(m),
    replaceStations: (rows) => (seen.stations = new Map(Object.entries(rows))),
    replacePackets: (rows) => (seen.packets = new Map(Object.entries(rows))),
    replaceMessages: (rows) => (seen.messages = new Map(Object.entries(rows))),
    replaceBulletins: (rows) => (seen.bulletins = new Map(Object.entries(rows))),
    replaceStationPrefs: (rows) => (seen.prefs = new Map(Object.entries(rows))),
    replaceOwnObjects: (rows) => (seen.ownObjects = new Map(Object.entries(rows))),
    replaceOwnBulletins: (rows) => (seen.ownBulletins = new Map(Object.entries(rows))),
    replaceTnc: (v) => (seen.tnc = v),
    replaceConfig: (v) => (seen.config = v),
    replaceMap: (v) => (seen.map = v),
    replaceUpdate: (v) => (seen.update = v),
    replaceGps: (v) => (seen.gps = v),
    replaceIgate: (v) => (seen.igate = v),
    setStation: (k, r) => void seen.stations.set(k, r),
    setPacket: (k, r) => void seen.packets.set(k, r),
    setMessage: (k, r) => void seen.messages.set(k, r),
    setBulletin: (k, r) => void seen.bulletins.set(k, r),
    setStationPref: (k, p) => void seen.prefs.set(k, p),
    setOwnObject: (k, r) => void seen.ownObjects.set(k, r),
    setOwnBulletin: (k, r) => void seen.ownBulletins.set(k, r),
    delStation: (k) => void seen.stations.delete(k),
    delPacket: (k) => void seen.packets.delete(k),
    delMessage: (k) => void seen.messages.delete(k),
    delBulletin: (k) => void seen.bulletins.delete(k),
    delStationPref: (k) => void seen.prefs.delete(k),
    delOwnObject: (k) => void seen.ownObjects.delete(k),
    delOwnBulletin: (k) => void seen.ownBulletins.delete(k),
  };
  return { seen, store };
}

const state = (topic: string, rev: number, value: unknown) => ({ type: "state", topic, rev, value });
const patch = (topic: string, rev: number, ops: object[]) => ({ type: "patch", topic, rev, ops });

describe("Hub", () => {
  beforeEach(() => {
    FakeSocket.all = [];
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  function opened(onHello?: (message: HelloMessage) => void) {
    const m = memory();
    const hub = new Hub(m.store, { url: () => "ws://host/ws", socket: (url) => new FakeSocket(url), onHello });
    hub.open();
    return { ...m, hub, socket: FakeSocket.last() };
  }

  it("connects to the url it is given and is open at the first message", () => {
    const { seen, socket } = opened();
    expect(socket.url).toBe("ws://host/ws");
    expect(seen.connection).toEqual(["connecting"]);
    socket.say({ type: "hello", protocol: PROTOCOL, version: "0.1", topics: [] });
    expect(seen.connection).toEqual(["connecting", "open"]);
    expect(seen.hello).toBe(1);
  });

  it("puts the state of every topic where it belongs", () => {
    const { seen, socket } = opened();
    socket.say(state("stations", 0, { A: station("A") }));
    socket.say(state("packets", 0, { "1": packet(1) }));
    socket.say(state("tnc", 0, tncState()));
    socket.say(state("config", 0, configValues()));
    socket.say(state("map", 0, mapState({ state: "ready", detail: mapFile() })));
    socket.say(state("messages", 0, { "4": message(4) }));
    socket.say({ type: "status", version: "0.1", started_at: "2026-10-21T00:00:00Z", packets: 1, stations: 1, call: "OH2GBA", lat: 60, lon: 24 });
    expect([...seen.messages.keys()]).toEqual(["4"]);
    expect([...seen.stations.keys()]).toEqual(["A"]);
    expect([...seen.packets.keys()]).toEqual(["1"]);
    expect(seen.tnc?.state).toBe("connected");
    expect(seen.config).toEqual(configValues());
    expect(seen.map).toEqual(mapState({ state: "ready", detail: mapFile() }));
    expect(seen.statuses).toBe(1);
  });

  it("replaces the map as a whole when the daemon patches it", () => {
    const { seen, socket } = opened();
    socket.say(state("map", 3, mapState()));
    socket.say(patch("map", 4, [{ op: "replace", value: mapState({ state: "downloading", step: "world", percent: 42 }) }]));
    expect(seen.map).toEqual(mapState({ state: "downloading", step: "world", percent: 42 }));
  });

  it("puts the GPS topic in the store of the GPS, not in the settings", () => {
    const { seen, socket } = opened();
    socket.say(state("config", 0, configValues()));
    socket.say(state("gps", 0, gpsState()));
    socket.say(patch("gps", 1, [{ op: "replace", value: gpsState({ state: "stale" }) }]));
    expect((seen.gps as GpsState).state).toBe("stale");
    expect(seen.config).toEqual(configValues());
  });

  it("puts the iGate topic in the store of the iGate, told whole", () => {
    const { seen, socket } = opened();
    socket.say(state("igate", 0, igateState()));
    socket.say(patch("igate", 1, [{ op: "replace", value: igateState({ state: "unverified", gated: 0 }) }]));
    expect((seen.igate as IgateState).state).toBe("unverified");
    expect(seen.gps).toBeNull();
  });

  it("applies set, del and replace ops in order", () => {
    const { seen, socket } = opened();
    socket.say(state("stations", 4, { A: station("A") }));
    socket.say(
      patch("stations", 5, [
        { op: "set", key: "B", value: station("B") },
        { op: "set", key: "A", value: station("A", { packets: 9 }) },
        { op: "del", key: "B" },
      ]),
    );
    expect([...seen.stations.keys()]).toEqual(["A"]);
    expect(seen.stations.get("A")?.packets).toBe(9);
    socket.say(state("tnc", 0, tncState()));
    socket.say(patch("tnc", 1, [{ op: "replace", value: tncState({ state: "waiting" }) }]));
    expect(seen.tnc?.state).toBe("waiting");
    socket.say(patch("stations", 6, [{ op: "replace", value: { Z: station("Z") } }]));
    expect([...seen.stations.keys()]).toEqual(["Z"]);
  });

  it("follows the messages by their ids: a message that changes is set again, one that is gone is deleted", () => {
    const { seen, socket } = opened();
    socket.say(state("messages", 0, { "1": message(1), "2": message(2) }));
    socket.say(
      patch("messages", 1, [
        { op: "set", key: "2", value: message(2, { state: "acked" }) },
        { op: "set", key: "3", value: message(3) },
        { op: "del", key: "1" },
      ]),
    );
    expect([...seen.messages.keys()]).toEqual(["2", "3"]);
    expect(seen.messages.get("2")?.state).toBe("acked");
  });

  it("hands the answer to weather_series to the store as it is", () => {
    const { seen, socket } = opened();
    const answer = { type: "weather_series", call: "OH2MUI", hours: 24, points: [["2026-10-21T12:00:00Z", 10, 1028.4, 1.6, 1.6, 0.3, 85]] };
    socket.say(answer);
    expect(seen.series).toEqual([answer]);
  });

  it("hands the answer to alert_test to the store as it is", () => {
    const { seen, socket } = opened();
    const answer = { type: "alert_result", ok: false, text: "exit code 3: no display" };
    socket.say(answer);
    expect(seen.alerts).toEqual([answer]);
  });

  it("hands the answer to list_ports to the store as it is", () => {
    const { seen, socket } = opened();
    const answer = {
      type: "ports",
      ports: [{ device: "/dev/ttyUSB0", description: "FT232R USB UART", hwid: "USB VID:PID=0403:6001", vid: 1027, pid: 24577 }],
      search: true,
      find: true,
    };
    socket.say(answer);
    expect(seen.ports).toEqual([answer]);
  });

  it("hands the steps and the end of find_radio to the store as they are", () => {
    const { seen, socket } = opened();
    const trying = { type: "radio_search", state: "trying", port: "/dev/ttyUSB0", baud: 9600, profile: "", number: 1, total: 14 };
    const found = { type: "radio_search", state: "found", port: "/dev/ttyUSB0", baud: 9600, profile: "kenwood-tnc2", number: 0, total: 0 };
    socket.say(trying);
    socket.say(found);
    expect(seen.searches).toEqual([trying, found]);
  });

  it("follows the message board by sender and slot: a bulletin heard again is set again, one that was deleted is gone", () => {
    const { seen, socket } = opened();
    socket.say(state("bulletins", 0, { "OH2XYZ/BLN1": bulletin("BLN1"), "OH2ABC/BLNA": bulletin("BLNA", { sender: "OH2ABC", kind: "announcement" }) }));
    socket.say(
      patch("bulletins", 1, [
        { op: "set", key: "OH2XYZ/BLN1", value: bulletin("BLN1", { times_heard: 2 }) },
        { op: "del", key: "OH2ABC/BLNA" },
      ]),
    );
    expect([...seen.bulletins.keys()]).toEqual(["OH2XYZ/BLN1"]);
    expect(seen.bulletins.get("OH2XYZ/BLN1")?.times_heard).toBe(2);
    socket.say(patch("bulletins", 2, [{ op: "replace", value: { "OH2DEF/QST": bulletin("QST", { sender: "OH2DEF", kind: "group" }) } }]));
    expect([...seen.bulletins.keys()]).toEqual(["OH2DEF/QST"]);
  });

  it("follows our own objects by name: one made or sent is set, one that is gone is deleted, and a whole table replaces the rest", () => {
    const { seen, socket } = opened();
    socket.say(state("own_objects", 0, { LEADER: ownObject("LEADER"), AID: ownObject("AID", { kind: "item" }) }));
    socket.say(
      patch("own_objects", 1, [
        { op: "set", key: "LEADER", value: ownObject("LEADER", { sent: 3, state: "killing" }) },
        { op: "del", key: "AID" },
      ]),
    );
    expect([...seen.ownObjects.keys()]).toEqual(["LEADER"]);
    expect(seen.ownObjects.get("LEADER")).toMatchObject({ sent: 3, state: "killing" });
    socket.say(patch("own_objects", 2, [{ op: "replace", value: { MARK: ownObject("MARK") } }]));
    expect([...seen.ownObjects.keys()]).toEqual(["MARK"]);
    expect(seen.tnc).toBeNull();
    expect(seen.config).toBeNull();
  });

  it("follows our own bulletins by slot: one posted or sent is set, one that is deleted is gone", () => {
    const { seen, socket } = opened();
    socket.say(state("own_bulletins", 0, { BLN1: ownBulletin("BLN1"), BLNA: ownBulletin("BLNA", { kind: "announcement" }) }));
    socket.say(
      patch("own_bulletins", 1, [
        { op: "set", key: "BLN1", value: ownBulletin("BLN1", { sent: 3, next_at: null }) },
        { op: "del", key: "BLNA" },
      ]),
    );
    expect([...seen.ownBulletins.keys()]).toEqual(["BLN1"]);
    expect(seen.ownBulletins.get("BLN1")).toMatchObject({ sent: 3, next_at: null });
    expect(seen.config).toBeNull();
  });

  it("follows what is set for the stations: a path (an empty one is direct) and a timeout, each null where none is set", () => {
    const { seen, socket } = opened();
    socket.say(state("station_prefs", 0, { OH2RDG: { path: "WIDE2-1" } }));
    socket.say(
      patch("station_prefs", 1, [
        { op: "set", key: "OH2XYZ", value: { path: null } },
        { op: "set", key: "OH2RDG", value: { path: "OH2RCH-2,WIDE2-1" } },
      ]),
    );
    expect([...seen.prefs.entries()]).toEqual([
      ["OH2RDG", { path: "OH2RCH-2,WIDE2-1" }],
      ["OH2XYZ", { path: null }],
    ]);
    socket.say(patch("station_prefs", 2, [{ op: "del", key: "OH2RDG" }]));
    expect([...seen.prefs.keys()]).toEqual(["OH2XYZ"]);
  });

  it("asks for a topic again when a revision is skipped, and ignores one it has", () => {
    const { seen, socket } = opened();
    socket.say({ type: "hello", protocol: PROTOCOL, version: "0.1", topics: [] });
    socket.say(state("packets", 3, {}));
    socket.say(patch("packets", 5, [{ op: "set", key: "9", value: packet(9) }]));
    expect(seen.packets.size).toBe(0);
    expect(socket.sent).toEqual([{ cmd: "subscribe", topics: ["packets"] }]);
    socket.say(patch("packets", 3, [{ op: "set", key: "9", value: packet(9) }]));
    expect(seen.packets.size).toBe(0);
    expect(socket.sent).toHaveLength(1);
    socket.say(state("packets", 5, { "9": packet(9) }));
    socket.say(patch("packets", 6, [{ op: "del", key: "9" }]));
    expect(seen.packets.size).toBe(0);
  });

  it("asks for a topic whose state it never had", () => {
    const { socket } = opened();
    socket.say({ type: "hello", protocol: PROTOCOL, version: "0.1", topics: [] });
    socket.say(patch("tnc", 1, [{ op: "replace", value: tncState() }]));
    expect(socket.sent).toEqual([{ cmd: "subscribe", topics: ["tnc"] }]);
  });

  it("hands an error to the store and ignores what it does not understand", () => {
    const { seen, socket } = opened();
    socket.say(errorOf("set_config: station/lat: 95 is not between -90 and 90", "setting.range", { value: 95, min: -90, max: 90 }));
    socket.onmessage?.(new MessageEvent("message", { data: "not json" }));
    socket.onmessage?.(new MessageEvent("message", { data: JSON.stringify({ type: "unheard-of" }) }));
    socket.onmessage?.(new MessageEvent("message", { data: JSON.stringify([1, 2]) }));
    socket.say(state("nosuchtopic", 1, {}));
    socket.say(state("stations", 1, "not an object"));
    expect(seen.errors).toEqual([
      {
        type: "error",
        cmd: "set_config",
        key: "station/lat",
        code: "setting.range",
        params: { value: 95, min: -90, max: 90 },
        text: "set_config: station/lat: 95 is not between -90 and 90",
      },
    ]);
    expect(seen.stations.size).toBe(0);
  });

  it("hands every hello to the caller, which decides whether the page is out of date", () => {
    const onHello = vi.fn<(message: HelloMessage) => void>();
    const { socket } = opened(onHello);
    socket.say(hello({ protocol: PROTOCOL + 1, version: "9" }));
    socket.say(hello());
    expect(onHello.mock.calls.map(([m]) => [m.protocol, m.version])).toEqual([
      [PROTOCOL + 1, "9"],
      [PROTOCOL, hello().version],
    ]);
  });

  it("hands the answer to update_check to the store as it is", () => {
    const { seen, socket } = opened();
    const answer = { type: "update_result", outcome: "newer", version: "0.4.0", text: "" };
    socket.say(answer);
    expect(seen.updates).toEqual([answer]);
  });

  it("sends commands only while the socket is open", () => {
    const { hub, socket } = opened();
    expect(hub.send({ cmd: "ping" })).toBe(false);
    socket.say({ type: "hello", protocol: PROTOCOL, version: "0.1", topics: [] });
    expect(hub.send({ cmd: "forget_station", call: "A" })).toBe(true);
    expect(socket.sent).toEqual([{ cmd: "forget_station", call: "A" }]);
  });

  it("opens the socket again after a wait that doubles, and starts over once the daemon speaks", () => {
    const { seen, socket } = opened();
    socket.hangUp();
    expect(seen.connection.at(-1)).toBe("closed");
    expect(FakeSocket.all).toHaveLength(1);
    vi.advanceTimersByTime(FIRST_DELAY_MS);
    expect(FakeSocket.all).toHaveLength(2);
    FakeSocket.last().hangUp();
    vi.advanceTimersByTime(FIRST_DELAY_MS);
    expect(FakeSocket.all).toHaveLength(2);
    vi.advanceTimersByTime(FIRST_DELAY_MS);
    expect(FakeSocket.all).toHaveLength(3);
    FakeSocket.last().say({ type: "hello", protocol: PROTOCOL, version: "0.1", topics: [] });
    FakeSocket.last().hangUp();
    vi.advanceTimersByTime(FIRST_DELAY_MS);
    expect(FakeSocket.all).toHaveLength(4);
  });

  it("starts from the whole state again after a reconnect", () => {
    const { seen, socket } = opened();
    socket.say(state("packets", 7, { "1": packet(1) }));
    socket.hangUp();
    vi.advanceTimersByTime(FIRST_DELAY_MS);
    const second = FakeSocket.last();
    second.say(patch("packets", 1, [{ op: "set", key: "2", value: packet(2) }])); // a new run of the daemon counts from 0 again
    expect(second.sent).toEqual([{ cmd: "subscribe", topics: ["packets"] }]);
    second.say(state("packets", 0, { "2": packet(2) }));
    expect([...seen.packets.keys()]).toEqual(["2"]);
  });

  it("does not open again after close()", () => {
    const { hub, socket, seen } = opened();
    hub.close();
    expect(socket.closed).toBe(true);
    expect(seen.connection.at(-1)).toBe("closed");
    socket.hangUp();
    vi.advanceTimersByTime(MAX_DELAY_MS * 2);
    expect(FakeSocket.all).toHaveLength(1);
  });

  it("says so when a socket closes before the daemon has said anything (it may have been refused), and not when one that was open closes", () => {
    const m = memory();
    const refused = vi.fn();
    const hub = new Hub(m.store, { url: () => "ws://host/ws", socket: (url) => new FakeSocket(url), refused });
    hub.open();
    FakeSocket.last().hangUp();
    expect(refused).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(FIRST_DELAY_MS);
    FakeSocket.last().say({ type: "hello", protocol: PROTOCOL, version: "0.1", topics: [] });
    FakeSocket.last().hangUp();
    expect(refused).toHaveBeenCalledTimes(1);
  });

  it("waits no longer than 30 seconds", () => {
    let delay = FIRST_DELAY_MS;
    for (let i = 0; i < 10; i++) delay = nextDelay(delay);
    expect(delay).toBe(MAX_DELAY_MS);
  });

  it("tells a frame that is a message from one that is not", () => {
    expect(parseMessage('{"type":"pong","now":"2026-10-21T00:00:00Z"}')?.type).toBe("pong");
    expect(parseMessage("{")).toBeNull();
    expect(parseMessage('{"type":5}')).toBeNull();
  });
});
