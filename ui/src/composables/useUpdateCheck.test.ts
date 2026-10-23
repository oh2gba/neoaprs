import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, shallowRef } from "vue";
import type { Toast } from "@/composables/useDaemon";
import { outcomeOf, SHOWN_MS, useUpdateCheck } from "@/composables/useUpdateCheck";
import type { UpdateResultMessage } from "@/protocol/protocol";
import { toastOf } from "@/test/fixtures";

const answer = (extra: Partial<UpdateResultMessage>): UpdateResultMessage => ({
  type: "update_result",
  outcome: "current",
  version: "0.3.0",
  text: "",
  ...extra,
});

function setUp(sends = true) {
  const result = shallowRef<UpdateResultMessage | null>(null);
  const error = shallowRef<Toast | null>(null);
  const send = vi.fn(() => sends);
  const scope = effectScope();
  const check = scope.run(() => useUpdateCheck(result, error, send));
  if (!check) throw new Error("no scope");
  return { check, result, error, send, scope };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("outcomeOf", () => {
  it("has a few words for each answer", () => {
    expect(outcomeOf(answer({}))).toEqual({ text: "up to date (0.3.0)", newer: false });
    expect(outcomeOf(answer({ outcome: "newer", version: "0.4.0" }))).toEqual({ text: "0.4.0 available", newer: true });
    expect(outcomeOf(answer({ outcome: "no_answer", version: "", text: "the version page could not be reached" }))).toEqual({
      text: "the version page could not be reached",
      newer: false,
    });
    expect(outcomeOf(answer({ outcome: "no_answer", version: "" })).text).toBe("no answer");
  });
});

describe("useUpdateCheck", () => {
  it("sends update_check and waits until the answer comes", async () => {
    const { check, result, send } = setUp();
    check.check();
    expect(send).toHaveBeenCalledWith({ cmd: "update_check" });
    expect(check.running.value).toBe(true);
    check.check();
    expect(send).toHaveBeenCalledTimes(1);
    result.value = answer({});
    await vi.advanceTimersByTimeAsync(0);
    expect(check.running.value).toBe(false);
    expect(check.outcome.value?.text).toBe("up to date (0.3.0)");
  });

  it("shows the answer for a few seconds and then nothing", async () => {
    const { check, result } = setUp();
    check.check();
    result.value = answer({ outcome: "newer", version: "0.4.0" });
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(SHOWN_MS - 1);
    expect(check.outcome.value?.text).toBe("0.4.0 available");
    await vi.advanceTimersByTimeAsync(1);
    expect(check.outcome.value).toBeNull();
  });

  it("ignores an answer nobody asked for", async () => {
    const { check, result } = setUp();
    result.value = answer({});
    await vi.advanceTimersByTimeAsync(0);
    expect(check.outcome.value).toBeNull();
  });

  it("does not wait when the socket is not open", () => {
    const { check } = setUp(false);
    check.check();
    expect(check.running.value).toBe(false);
  });

  it("shows the error of the daemon in place of an answer", async () => {
    const { check, error } = setUp();
    check.check();
    error.value = toastOf("update_check: the database is busy");
    await vi.advanceTimersByTimeAsync(0);
    expect(check.running.value).toBe(false);
    expect(check.outcome.value?.text).toBe("the database is busy");
  });

  it("leaves the error of another command alone", async () => {
    const { check, error } = setUp();
    check.check();
    error.value = toastOf("set_config: station/lat: 95 is out", "setting.range");
    await vi.advanceTimersByTimeAsync(0);
    expect(check.running.value).toBe(true);
    expect(check.outcome.value).toBeNull();
  });

  it("clears the earlier answer when it asks again", async () => {
    const { check, result } = setUp();
    check.check();
    result.value = answer({});
    await vi.advanceTimersByTimeAsync(0);
    check.check();
    expect(check.outcome.value).toBeNull();
  });

  it("stops its timer with its scope", async () => {
    const { check, result, scope } = setUp();
    check.check();
    result.value = answer({});
    await vi.advanceTimersByTimeAsync(0);
    scope.stop();
    expect(vi.getTimerCount()).toBe(0);
  });
});
