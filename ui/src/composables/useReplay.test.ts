import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, shallowRef } from "vue";
import { useReplay } from "@/composables/useReplay";
import type { Command, IgateState, PositionHistoryMessage } from "@/protocol/protocol";
import { igateState } from "@/test/fixtures";

const START = "2026-10-21T09:00:00Z";
const T0 = Date.parse(START);
const HOUR = 3_600_000;

function answer(hours = 3): PositionHistoryMessage {
  return { type: "position_history", hours, start: START, end: new Date(T0 + hours * HOUR).toISOString(), stations: { OH2RDG: [[START, 60, 25]] } };
}

function setUp(connected = true) {
  const positionHistory = shallowRef<PositionHistoryMessage | null>(null);
  const igate = shallowRef<IgateState | null>(igateState({ enabled: true }));
  const send = vi.fn((_command: Command) => connected);
  const scope = effectScope();
  const replay = scope.run(() => useReplay({ send, positionHistory, igate }));
  if (!replay) throw new Error("no replay");
  return { replay, send, positionHistory, igate, scope };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("the replay's clock", () => {
  it("asks for the span and plays it from its start when the answer comes", async () => {
    const { replay, send, positionHistory } = setUp();
    replay.ask();
    expect(send).toHaveBeenCalledWith({ cmd: "position_history", hours: 3 });
    expect(replay.loading.value).toBe(true);
    positionHistory.value = answer();
    await nextTick();
    expect(replay.loading.value).toBe(false);
    expect(replay.data.value?.tracks).toHaveLength(1);
    expect(replay.at.value).toBe(T0);
    expect(replay.playing.value).toBe(true);
  });

  it("takes only the answer to what it asked: not another span's, nor one that came before it asked", async () => {
    const { replay, positionHistory } = setUp();
    positionHistory.value = answer();
    await nextTick();
    expect(replay.data.value).toBeNull();
    replay.ask(6);
    positionHistory.value = answer(3);
    await nextTick();
    expect(replay.data.value).toBeNull();
    positionHistory.value = answer(6);
    await nextTick();
    expect(replay.data.value?.hours).toBe(6);
    expect(replay.hours.value).toBe(6);
  });

  it("is not waiting when the command could not be sent", () => {
    const { replay } = setUp(false);
    replay.ask();
    expect(replay.loading.value).toBe(false);
  });

  it("runs at its speed, stops at the end of the span, and plays again from the start", async () => {
    const { replay, positionHistory } = setUp();
    replay.ask(1);
    positionHistory.value = answer(1);
    await nextTick();
    vi.advanceTimersByTime(1000);
    expect(replay.at.value).toBe(T0 + 300_000); // (300 times: a second is five minutes)
    replay.pace(3600);
    vi.advanceTimersByTime(2000);
    expect(replay.at.value).toBe(T0 + HOUR);
    expect(replay.playing.value).toBe(false);
    replay.toggle();
    expect(replay.at.value).toBe(T0);
    expect(replay.playing.value).toBe(true);
  });

  it("pauses, seeks inside the span, and does not run while the tab is hidden", async () => {
    const { replay, positionHistory } = setUp();
    replay.ask();
    positionHistory.value = answer();
    await nextTick();
    replay.toggle();
    await nextTick();
    vi.advanceTimersByTime(5000);
    expect(replay.at.value).toBe(T0);
    replay.seek(T0 - HOUR);
    expect(replay.at.value).toBe(T0);
    replay.seek(T0 + 10 * HOUR);
    expect(replay.at.value).toBe(T0 + 3 * HOUR);
    replay.seek(T0 + HOUR);
    replay.toggle();
    await nextTick();
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    vi.advanceTimersByTime(5000);
    expect(replay.at.value).toBe(T0 + HOUR);
    hidden.mockRestore();
    vi.advanceTimersByTime(100);
    expect(replay.at.value).toBe(T0 + HOUR + 30_000); // (the hidden time is not made up for)
  });

  it("asks again when Internet stations is switched while it is open, and plays on from where it was", async () => {
    const { replay, send, positionHistory, igate } = setUp();
    replay.ask(6);
    positionHistory.value = answer(6);
    await nextTick();
    replay.seek(T0 + HOUR);
    replay.toggle(); // (paused)
    igate.value = igateState({ enabled: false });
    await nextTick();
    expect(send).toHaveBeenCalledTimes(2);
    expect(send).toHaveBeenLastCalledWith({ cmd: "position_history", hours: 6 });
    expect(replay.data.value).toBeNull(); // (the old set is not shown while the new one comes)
    positionHistory.value = answer(6);
    await nextTick();
    expect(replay.data.value?.hours).toBe(6);
    expect(replay.at.value).toBe(T0 + HOUR);
    expect(replay.playing.value).toBe(false);
    igate.value = igateState({ enabled: false, gated: 99 }); // (the topic told again, the switch the same)
    await nextTick();
    expect(send).toHaveBeenCalledTimes(2);
  });

  it("asks nothing when Internet stations is switched while it is closed, or before the iGate's state has come", async () => {
    const { replay, send, igate } = setUp();
    igate.value = igateState({ enabled: false });
    await nextTick();
    expect(send).not.toHaveBeenCalled();
    replay.ask();
    replay.stop();
    igate.value = igateState({ enabled: true });
    await nextTick();
    expect(send).toHaveBeenCalledTimes(1);
    igate.value = null;
    replay.ask();
    await nextTick();
    igate.value = igateState({ enabled: true });
    await nextTick();
    expect(send).toHaveBeenCalledTimes(2);
  });

  it("forgets the span when it stops, and its timer goes with its scope", async () => {
    const { replay, positionHistory, scope } = setUp();
    replay.ask();
    positionHistory.value = answer();
    await nextTick();
    replay.stop();
    await nextTick();
    expect(replay.data.value).toBeNull();
    expect(replay.playing.value).toBe(false);
    replay.toggle(); // (nothing to play)
    expect(replay.playing.value).toBe(false);
    scope.stop();
    expect(vi.getTimerCount()).toBe(0);
  });
});
