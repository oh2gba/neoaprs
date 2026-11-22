import { afterEach, describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, ref, shallowRef } from "vue";
import type { Toast } from "@/composables/useDaemon";
import { ANSWER_MS, useInFlight } from "@/composables/useInFlight";
import type { Connection } from "@/lib/hub";
import { toastOf } from "@/test/fixtures";

function setUp() {
  const answer = ref(0);
  const lastError = shallowRef<Toast | null>(null);
  const connection = ref<Connection>("open");
  const scope = effectScope();
  const flight = scope.run(() => useInFlight("general_query", answer, { lastError, connection }));
  if (flight === undefined) throw new Error("no scope");
  const send = vi.fn(() => true);
  return { answer, lastError, connection, flight, send, scope };
}

afterEach(() => vi.useRealTimers());

describe("useInFlight", () => {
  it("sends once while in flight, and again once the answer is told", async () => {
    const { answer, flight, send } = setUp();
    expect(flight.run(send)).toBe(true);
    expect(flight.run(send)).toBe(false);
    expect(send).toHaveBeenCalledTimes(1);
    answer.value += 1;
    await nextTick();
    expect(flight.busy.value).toBe(false);
    expect(flight.run(send)).toBe(true);
  });

  it("is not in flight when nothing went", () => {
    const { flight } = setUp();
    expect(flight.run(() => false)).toBe(false);
    expect(flight.busy.value).toBe(false);
  });

  it("lands on a refusal of its command only", async () => {
    const { lastError, flight, send } = setUp();
    flight.run(send);
    lastError.value = toastOf("qru_ask: RX only", "transmit.off");
    await nextTick();
    expect(flight.busy.value).toBe(true);
    lastError.value = toastOf("general_query: RX only", "transmit.off");
    await nextTick();
    expect(flight.busy.value).toBe(false);
  });

  it("lands when the socket closes, since the answer is lost with it", async () => {
    const { connection, flight, send } = setUp();
    flight.run(send);
    connection.value = "closed";
    await nextTick();
    expect(flight.busy.value).toBe(false);
  });

  it("lands after the time it may wait", () => {
    vi.useFakeTimers();
    const { flight, send, scope } = setUp();
    flight.run(send);
    vi.advanceTimersByTime(ANSWER_MS - 1);
    expect(flight.busy.value).toBe(true);
    vi.advanceTimersByTime(1);
    expect(flight.busy.value).toBe(false);
    scope.stop();
  });
});
