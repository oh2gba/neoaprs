import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSure } from "@/composables/useSure";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useSure", () => {
  it("arms on the first press and acts on the second", () => {
    const sure = useSure<number>();
    const act = vi.fn();
    sure.press(1, act);
    expect([sure.armed.value, act.mock.calls.length]).toEqual([1, 0]);
    sure.press(1, act);
    expect([sure.armed.value, act.mock.calls.length]).toEqual([null, 1]);
  });

  it("disarms after the time, 5 seconds unless said", () => {
    const sure = useSure<number>();
    sure.press(1, vi.fn());
    vi.advanceTimersByTime(4999);
    expect(sure.armed.value).toBe(1);
    vi.advanceTimersByTime(2);
    expect(sure.armed.value).toBeNull();
    const quick = useSure<string>(100);
    quick.press("a", vi.fn());
    vi.advanceTimersByTime(101);
    expect(quick.armed.value).toBeNull();
  });

  it("is armed for one key at a time, and arming another starts the time again", () => {
    const sure = useSure<number>();
    const act = vi.fn();
    sure.press(1, act);
    vi.advanceTimersByTime(4000);
    sure.press(2, act);
    expect(sure.armed.value).toBe(2);
    vi.advanceTimersByTime(4000);
    expect(sure.armed.value).toBe(2);
    sure.press(1, act);
    expect(act).not.toHaveBeenCalled();
  });
});
