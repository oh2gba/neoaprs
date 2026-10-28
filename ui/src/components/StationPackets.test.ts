import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { nextTick, shallowRef } from "vue";
import StationCards from "@/components/StationCards.vue";
import type { PacketHistoryMessage } from "@/protocol/protocol";
import { fakeDaemon, withDaemon } from "@/test/context";
import { NOW, station } from "@/test/fixtures";

afterEach(() => document.body.replaceChildren());

const START = "2026-10-20T13:00:00Z"; // (the top of the hour 23 hours before NOW's)
const answer = (call: string, counts: number[]): PacketHistoryMessage => ({ type: "packet_history", hours: 24, call, start: START, counts });

function make(rows: ReturnType<typeof station>[]) {
  const now = shallowRef(NOW);
  const histories = shallowRef<ReadonlyMap<string, PacketHistoryMessage>>(new Map());
  const daemon = fakeDaemon({ now, packetHistoryByCall: histories });
  const wrapper = mount(StationCards, { props: { rows, size: "desktop" }, global: withDaemon(daemon), attachTo: document.body });
  return { wrapper, daemon, now, histories };
}

describe("the packets of a station on its card", () => {
  it("are asked for with the station's call when the card opens, and again each minute", async () => {
    const { daemon, now } = make([station("OH2RDG"), station("OH2XYZ")]);
    expect(daemon.send).toHaveBeenCalledWith({ cmd: "packet_history", call: "OH2RDG", hours: 24 });
    expect(daemon.send).toHaveBeenCalledWith({ cmd: "packet_history", call: "OH2XYZ", hours: 24 });
    daemon.send.mockClear();
    now.value = NOW + 30_000;
    await nextTick();
    expect(daemon.send).not.toHaveBeenCalled();
    now.value = NOW + 60_000;
    await nextTick();
    expect(daemon.send.mock.calls.map(([c]) => c)).toEqual([
      { cmd: "packet_history", call: "OH2RDG", hours: 24 },
      { cmd: "packet_history", call: "OH2XYZ", hours: 24 },
    ]);
  });

  it("are 24 bars from the card's own answer, and the answer for another station is not drawn on it", async () => {
    const { wrapper, histories } = make([station("OH2RDG")]);
    const graph = () => wrapper.find("[data-packets]");
    expect(graph().find(".trend-head").text()).toContain("Packets an hour, the last 24 hours");
    expect(graph().findAll(".trend-bar")).toHaveLength(0);
    histories.value = new Map([
      [
        "OH2XYZ",
        answer(
          "OH2XYZ",
          Array.from({ length: 24 }, () => 5),
        ),
      ],
    ]);
    await nextTick();
    expect(graph().findAll(".trend-bar")).toHaveLength(0);
    histories.value = new Map([
      ...histories.value,
      [
        "OH2RDG",
        answer(
          "OH2RDG",
          Array.from({ length: 24 }, (_, i) => i + 1),
        ),
      ],
    ]);
    await nextTick();
    expect(graph().findAll(".trend-bar")).toHaveLength(24);
    expect(graph().find(".trend-read").text()).toMatch(/^24 packets\s+\d\d:\d\d:\d\d$/);
  });

  it("has its frame before the answer comes, over the same hours, so the card does not grow when the bars arrive", async () => {
    const { wrapper, histories } = make([station("OH2RDG")]);
    const ticks = () => wrapper.findAll("[data-packets] .trend-grid text").length;
    const before = { figures: wrapper.findAll("[data-packets] svg").length, xs: wrapper.findAll("[data-packets] .tick").map((l) => l.attributes("x1")) };
    expect(before.figures).toBe(1);
    expect(ticks()).toBeGreaterThan(0);
    histories.value = new Map([
      [
        "OH2RDG",
        answer(
          "OH2RDG",
          Array.from({ length: 24 }, () => 2),
        ),
      ],
    ]);
    await nextTick();
    expect(wrapper.findAll("[data-packets] svg")).toHaveLength(1);
    expect(wrapper.findAll("[data-packets] .tick").map((l) => l.attributes("x1"))).toEqual(before.xs);
  });

  it("are not on the card of our own station, of an object or of an item, and nothing is asked for them", () => {
    const { wrapper, daemon } = make([
      station("OH2GBA", { is_me: true }),
      station("LEADER", { kind: "object", reported_by: "OH2RDG" }),
      station("RACE", { kind: "item", own: true }),
    ]);
    expect(wrapper.findAll(".card")).toHaveLength(3);
    expect(wrapper.find("[data-packets]").exists()).toBe(false);
    expect(daemon.send.mock.calls.filter(([c]) => c.cmd === "packet_history")).toEqual([]);
  });
});
