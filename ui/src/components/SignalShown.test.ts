// Where the signal of what was heard is shown: under a message that came in, in a packet's detail, in a station's traffic, on the station's card (the row with the last time, the graph) and in the title of our message's mark. Nothing is shown, and nothing moves, for a packet without a reading.
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { nextTick, shallowRef } from "vue";
import ConversationThread from "@/components/ConversationThread.vue";
import MessageMark from "@/components/MessageMark.vue";
import PacketDetail from "@/components/PacketDetail.vue";
import PacketLines from "@/components/PacketLines.vue";
import StationCards from "@/components/StationCards.vue";
import StationTraffic from "@/components/StationTraffic.vue";
import type { SignalSeriesMessage, StationRow } from "@/protocol/protocol";
import { fakeDaemon, withDaemon } from "@/test/context";
import { NOW, ago, incoming, message, packet, station } from "@/test/fixtures";

afterEach(() => document.body.replaceChildren());

const MINUS = "\u2212";

describe("the signal under a message that came in", () => {
  const line = (extra: Parameters<typeof incoming>[2]) =>
    mount(ConversationThread, { props: { thread: [incoming(2, "OH2HF", extra)], peer: "OH2HF" } }).find(".bubble-route");

  it("ends the line that says how it came: HF direct, SNR -3 dB", () => {
    expect(line({ radio: "hf", route: "direct", snr: -3 }).text()).toBe(`HF direct \u00b7 SNR ${MINUS}3 dB`);
    expect(line({ radio: "fm", route: "via OH2RCH-2", snr: 4, rssi: -95 }).text()).toBe(`via OH2RCH-2 \u00b7 SNR 4 dB, RSSI ${MINUS}95 dBm`);
  });

  it("is the whole line when there is no route to say", () => {
    expect(line({ radio: "", route: "", snr: -3 }).text()).toBe(`SNR ${MINUS}3 dB`);
  });

  it("is not there for a message with no reading, and the line is as it was", () => {
    expect(line({ radio: "hf", route: "direct", snr: null }).text()).toBe("HF direct");
    const none = mount(ConversationThread, { props: { thread: [incoming(2, "OH2HF", { radio: "", route: "", snr: null })], peer: "OH2HF" } });
    expect(none.find(".bubble-route").exists()).toBe(false);
  });

  it("is not under a message of ours: the mark has the ack's", () => {
    const wrapper = mount(ConversationThread, { props: { thread: [message(1, { state: "acked", route: "", snr: -3 })], peer: "OH2HF" } });
    expect(wrapper.find(".bubble-route").exists()).toBe(false);
  });
});

describe("the SNR of the ack on the mark of our message", () => {
  const title = (extra: Parameters<typeof message>[1]) => mount(MessageMark, { props: { row: message(1, extra) } }).attributes("title");

  it("is added to the mark's title once the ack came", () => {
    expect(title({ state: "acked", acked_at: "2026-10-22T12:00:05Z", snr: -7 })).toMatch(new RegExp(`^acked .+ \u00b7 SNR ${MINUS}7 dB$`));
  });

  it("leaves the title as it was when the ack came with no reading, and for a message still being sent", () => {
    expect(title({ state: "acked", acked_at: null, snr: null })).toBe("acked");
    expect(title({ state: "sending", attempts: 2, attempts_max: 6, snr: null })).toBe("attempt 2 of 6");
  });
});

describe("the signal of a packet", () => {
  const detail = (extra: Parameters<typeof packet>[1]) =>
    Object.fromEntries(
      mount(PacketDetail, { props: { row: packet(1, extra) } })
        .findAll("dt")
        .map((dt) => [dt.text(), (dt.element.nextElementSibling as HTMLElement).textContent?.trim()]),
    );

  it("is a fact in its detail, between how it came and when", () => {
    const wrapper = mount(PacketDetail, { props: { row: packet(1, { snr: -3 }) } });
    const labels = wrapper.findAll("dt").map((dt) => dt.text());
    expect(labels.indexOf("Signal")).toBe(labels.indexOf("Heard") - 1);
    expect(labels.indexOf("Signal")).toBeGreaterThan(labels.indexOf("Came by"));
    expect(detail({ snr: -3 })["Signal"]).toBe(`SNR ${MINUS}3 dB`);
  });

  it("is not a fact of a packet with no reading, nor of one of ours", () => {
    expect(Object.keys(detail({ snr: null }))).not.toContain("Signal");
    expect(Object.keys(detail({ direction: "out", snr: -3 }))).not.toContain("Signal");
  });

  it("is under the detail of a line in the Packets tab and a station's traffic", () => {
    const wrapper = mount(PacketLines, { props: { rows: [packet(1, { snr: -3 })], stacked: false, empty: "none" } });
    return wrapper
      .find("tr.packet-row")
      .trigger("click")
      .then(() => expect(wrapper.find(".detail").text()).toContain(`SNR ${MINUS}3 dB`));
  });
});

describe("the signal in a station's traffic", () => {
  it("follows the summary of each packet the station sent that has a reading, and nothing is added to the others", () => {
    const rows = [packet(1, { source: "OH2HF", snr: -3 }), packet(2, { source: "OH2HF", snr: null, tnc2: "OH2HF>APRS:!2" })];
    const logged = new Map([["OH2HF", { type: "station_traffic" as const, call: "OH2HF", packets: rows }]]);
    const daemon = fakeDaemon({ now: NOW, stationTrafficByCall: shallowRef(logged) });
    const wrapper = mount(StationTraffic, { props: { call: "OH2HF" }, global: withDaemon(daemon), attachTo: document.body });
    const notes = wrapper.findAll("tr.packet-row").map((line) => line.find("[data-signal-note]").exists() && line.find("[data-signal-note]").text());
    expect(notes.filter((note) => note !== false)).toEqual([`\u00b7 SNR ${MINUS}3 dB`]);
    expect(notes.filter((note) => note === false)).toHaveLength(1);
  });
});

const hf = (extra: Partial<StationRow> = {}) => station("OH2HF", { snr: -3, rssi: null, signal_at: ago(300), last_heard: ago(60), ...extra });
const answer = (points: SignalSeriesMessage["points"]): SignalSeriesMessage => ({ type: "signal_series", call: "OH2HF", hours: 24, points });
const readings: SignalSeriesMessage["points"] = [
  [ago(7200), -8, null],
  [ago(3600), -3, null],
  [ago(300), 1, null],
];

function make(rows: StationRow[]) {
  const series = shallowRef<ReadonlyMap<string, SignalSeriesMessage>>(new Map());
  const daemon = fakeDaemon({ now: NOW, signalSeriesByCall: series });
  const wrapper = mount(StationCards, { props: { rows, size: "desktop" }, global: withDaemon(daemon), attachTo: document.body });
  const asked = () => daemon.send.mock.calls.map(([c]) => c).filter((c) => c.cmd === "signal_series");
  return { wrapper, series, asked };
}

describe("the signal on the station's card", () => {
  it("is a row under the last heard, with when it was and the full time as its title", () => {
    const { wrapper } = make([hf()]);
    const dts = wrapper.findAll("dt").map((dt) => dt.text());
    expect(dts.indexOf("Signal")).toBe(dts.indexOf("Last heard") + 1);
    const dd = wrapper.findAll("dd")[dts.indexOf("Signal")];
    expect(dd?.text()).toBe(`SNR ${MINUS}3 dB, 5 min ago`);
    expect(dd?.attributes("title")).toBeTruthy();
  });

  it("has no row, no graph and asks for nothing for a station with no reading", () => {
    const { wrapper, asked } = make([hf({ snr: null, rssi: null, signal_at: null })]);
    expect(wrapper.findAll("dt").map((dt) => dt.text())).not.toContain("Signal");
    expect(wrapper.find("[data-signal]").exists()).toBe(false);
    expect(asked()).toEqual([]);
  });

  it("asks for the readings of the last day with the card's call, and draws the line from its own answer", async () => {
    const { wrapper, series, asked } = make([hf()]);
    expect(asked()).toEqual([{ cmd: "signal_series", call: "OH2HF", hours: 24 }]);
    expect(wrapper.find("[data-signal] .trend-head").text()).toContain("Signal-to-noise of its packets");
    expect(wrapper.findAll("[data-signal] svg")).toHaveLength(1);
    series.value = new Map([["OH2XYZ", { ...answer(readings), call: "OH2XYZ" }]]);
    await nextTick();
    expect(wrapper.find("[data-signal] .trend-line").exists()).toBe(false);
    series.value = new Map([...series.value, ["OH2HF", answer(readings)]]);
    await nextTick();
    expect(wrapper.find("[data-signal] .trend-line").attributes("d")).toMatch(/^M/);
    expect(wrapper.find("[data-signal] .trend-read").text()).toMatch(/^1 dB\s+\d\d:\d\d:\d\d$/);
  });

  it("asks again when a new reading of the station comes", async () => {
    const { wrapper, asked } = make([hf()]);
    await wrapper.setProps({ rows: [{ ...hf(), signal_at: ago(5) }] });
    expect(asked()).toHaveLength(2);
  });

  it("keeps its frame for a station with fewer than two readings, so nothing moves when the answer comes", async () => {
    const { wrapper, series } = make([hf()]);
    expect(wrapper.find("[data-signal] svg").exists()).toBe(true);
    series.value = new Map([["OH2HF", answer([[ago(300), -3, null]])]]);
    await nextTick();
    expect(wrapper.find("[data-signal] svg").exists()).toBe(true);
    expect(wrapper.find("[data-signal] .trend-line").exists()).toBe(false);
  });

  it("has no graph, from the row, for a station whose latest reading is older than a day", () => {
    const { wrapper } = make([hf({ signal_at: ago(25 * 3600) })]);
    expect(wrapper.find("[data-signal]").exists()).toBe(false);
    expect(wrapper.findAll("dt").map((dt) => dt.text())).toContain("Signal");
  });

  it("has no row and no graph on an object's or an item's card: the signal is its sender's", () => {
    for (const kind of ["object", "item"] as const) {
      const { wrapper, asked } = make([hf({ kind, reported_by: "OH2XYZ" })]);
      expect(wrapper.findAll("dt").map((dt) => dt.text())).not.toContain("Signal");
      expect(wrapper.find("[data-signal]").exists()).toBe(false);
      expect(asked()).toEqual([]);
      wrapper.unmount();
    }
  });

  it("writes a reading in its readout as the row writes it: half up, a true minus, no minus on 0", async () => {
    const { wrapper, series } = make([hf({ snr: -2.5 })]);
    for (const [value, text] of [
      [-2.5, `${MINUS}2 dB`],
      [-0.4, "0 dB"],
    ] as const) {
      series.value = new Map([
        [
          "OH2HF",
          answer([
            [ago(3600), -8, null],
            [ago(300), value, null],
          ]),
        ],
      ]);
      await nextTick();
      expect(wrapper.find("[data-signal] .trend-read").text()).toMatch(new RegExp(`^${text}\\s+\\d\\d:`));
    }
    expect(wrapper.find("[data-signal] svg").text()).toContain(MINUS);
    expect(wrapper.find("[data-signal] svg").text()).not.toContain("-");
  });

  it("draws the RSSI in dBm for a station whose radio gives that and no SNR", async () => {
    const { wrapper, series } = make([hf({ snr: null, rssi: -97 })]);
    series.value = new Map([
      [
        "OH2HF",
        answer([
          [ago(3600), null, -100],
          [ago(300), null, -97],
        ]),
      ],
    ]);
    await nextTick();
    expect(wrapper.find("[data-signal] .trend-head").text()).toContain("Strength of its packets");
    expect(wrapper.find("[data-signal] .trend-read").text()).toMatch(/dBm/);
  });
});
