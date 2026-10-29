// The traffic of a station in its panel (StationTraffic): the daemon is asked for it, it is laid out as the Packets tab's lines (the same table, columns, cells, block layout and detail), the packets that come after the answer
// are added once each, none from the internet while Internet stations is off, and a query of ours says "waiting…", "answered" or "no answer" in the same room.
import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, shallowReactive, shallowRef } from "vue";
import PacketsLog from "@/components/PacketsLog.vue";
import StationTraffic from "@/components/StationTraffic.vue";
import { PACKETS_TABLE } from "@/lib/layout";
import { ANSWER_WAIT_MS } from "@/lib/stationtraffic";
import { fakeDaemon, withDaemon, type FakeDaemon } from "@/test/context";
import { configValues, NOW, packet, packetAt, sentMessage } from "@/test/fixtures";
import { stubWidth } from "@/test/width";
import type { ConfigValues, PacketRow, StationTrafficMessage } from "@/protocol/protocol";

let wrapper: VueWrapper;
let daemon: FakeDaemon;
let packets: Map<string, PacketRow>;
let width: ReturnType<typeof stubWidth> | undefined;
const answered = (rows: PacketRow[]) => new Map<string, StationTrafficMessage>([["OH2RDG", { type: "station_traffic", call: "OH2RDG", packets: rows }]]);
const position = (id: number, seconds: number, extra: Partial<PacketRow> = {}) =>
  packet(id, { heard_at: packetAt(seconds), tnc2: `OH2RDG>APRS:!${seconds}`, ...extra });
const make = (logged: PacketRow[] = [], internet = false) => {
  packets = shallowReactive(new Map<string, PacketRow>());
  daemon = fakeDaemon({
    packets,
    stationTrafficByCall: shallowRef(answered(logged)),
    config: shallowRef<ConfigValues | null>(configValues({ "igate/enabled": String(internet) })),
  });
  wrapper = mount(StationTraffic, { props: { call: "OH2RDG" }, attachTo: document.body, global: withDaemon(daemon) });
  return wrapper;
};
const lines = () => wrapper.findAll("tr.packet-row");
const states = () => wrapper.findAll(".querystate").map((s) => s.attributes("data-state"));

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});
afterEach(() => {
  wrapper.unmount();
  width?.restore();
  width = undefined;
  vi.useRealTimers();
  document.body.replaceChildren();
});

describe("the traffic of a station", () => {
  it("asks the daemon for the station's packets in its log", () => {
    make();
    expect(daemon.send).toHaveBeenCalledWith({ cmd: "station_traffic", call: "OH2RDG" });
    expect(wrapper.find("td.empty").text()).toBe("No packets of this station yet.");
  });

  it("is laid out as the Packets tab's lines: the same table, head and cells, line for line", async () => {
    const row = position(1, -60);
    make([row]);
    const log = mount(PacketsLog, { props: { packets: new Map([["1", row]]) }, global: withDaemon(daemon) });
    expect(wrapper.find("table").classes()).toEqual(log.find("table").classes());
    expect(wrapper.find("thead").html()).toBe(log.find("thead").html());
    expect(
      lines()[0]
        ?.findAll("td")
        .map((td) => [td.classes(), td.text()]),
    ).toEqual(
      log
        .find("tr.packet-row")
        .findAll("td")
        .map((td) => [td.classes(), td.text()]),
    );
    await lines()[0]?.trigger("click");
    expect(wrapper.find("tr.detail .packet-detail").exists()).toBe(true);
    log.unmount();
  });

  it("stacks each packet as one block when the panel is narrower than the Packets tab's table, as that tab does", async () => {
    width = stubWidth(PACKETS_TABLE - 1);
    make([position(1, -60)]);
    await nextTick();
    expect(wrapper.find("table").classes()).toContain("stacked");
    expect(wrapper.find("thead").classes()).toContain("sr-only");
  });

  it("adds the packets of the station that come after the answer, newest first, once each, and not the others'", async () => {
    make([position(900, -60), position(901, -120)]);
    packets.set("5", position(5, -60)); // (the log's newest, as the topic has it)
    packets.set("6", position(6, -5));
    packets.set("7", position(7, -4, { source: "OH2XYZ", tnc2: "OH2XYZ>APRS:!x" }));
    packets.set("8", sentMessage(8, "OH2GBA", "OH2RDG", "hello{01", -3));
    await nextTick();
    expect(lines().map((l) => l.find("td.line").text())).toEqual([
      "OH2GBA>APRS::OH2RDG   :hello{01",
      "OH2RDG>APRS:!-5",
      "OH2RDG>APRS:!-60",
      "OH2RDG>APRS:!-120",
    ]);
    packets.delete("6"); // (fallen out of the 200 of the topic: it stays here)
    await nextTick();
    expect(lines()).toHaveLength(4);
  });

  it("leaves out the packets from the internet while Internet stations is off, and shows them when it is on", async () => {
    const internet = position(2, -10, { via: "is", tnc2: "OH2RDG>APRS,TCPIP*,qAC,T2FINLAND:!x" });
    make([internet, position(1, -20)]);
    expect(lines()).toHaveLength(1);
    daemon.config.value = configValues({ "igate/enabled": "true" });
    await nextTick();
    expect(lines()).toHaveLength(2);
  });
});

describe("a query of ours in the traffic", () => {
  it("says waiting… after its summary, then no answer when two minutes have gone by without the answer", async () => {
    make([sentMessage(1, "OH2GBA", "OH2RDG", "?APRSP", 0)]);
    expect(states()).toEqual(["waiting"]);
    expect(wrapper.find(".querystate").text()).toContain("waiting…");
    vi.advanceTimersByTime(ANSWER_WAIT_MS - 1000);
    await nextTick();
    expect(states()).toEqual(["waiting"]);
    vi.advanceTimersByTime(2000);
    await nextTick();
    expect(states()).toEqual(["no_answer"]);
  });

  it("says answered when the answer it asks for comes from the station, and keeps one width: the three words are always there, two hidden", async () => {
    make([sentMessage(1, "OH2GBA", "OH2RDG", "?APRSS", 0)]);
    const words = () => wrapper.findAll(".querystate > span").map((s) => [s.text(), s.classes().includes("twowords-off")]);
    expect(words()).toEqual([
      ["waiting…", false],
      ["answered", true],
      ["no answer", true],
    ]);
    vi.advanceTimersByTime(5000);
    packets.set("2", position(2, 5)); // (a position: not what ?APRSS asks for)
    await nextTick();
    expect(states()).toEqual(["waiting"]);
    packets.set(
      "3",
      packet(3, {
        heard_at: packetAt(6),
        kind: "status",
        tnc2: "OH2RDG>APRS:>on",
        decoded: { type: "status", text: "on", locator: null, frequency: null, timestamp: null },
      }),
    );
    await nextTick();
    expect(states()).toEqual(["answered"]);
    expect(wrapper.find(".querystate").classes()).toContain("twowords");
    expect(words().map(([, off]) => off)).toEqual([true, false, true]);
    vi.advanceTimersByTime(ANSWER_WAIT_MS * 2);
    await nextTick();
    expect(states()).toEqual(["answered"]);
  });

  it("says nothing on a message of ours that is no query, nor on what the station sent", () => {
    make([
      sentMessage(1, "OH2GBA", "OH2RDG", "hello{01", 0, {
        decoded: { type: "message", addressee: "OH2RDG", text: "hello", msg_id: "01", ack_id: null, rej_id: null },
      }),
      position(2, -5),
    ]);
    expect(states()).toEqual([]);
  });
});
