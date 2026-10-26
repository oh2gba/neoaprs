import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ATTEND_MS, PAUSE_MS, attend } from "@/lib/attention";
import { cssRule } from "@/test/css";

beforeEach(() => {
  vi.useFakeTimers();
  document.body.innerHTML = `<form><fieldset id="g"><legend>Group</legend><div class="field"><input id="control" /></div></fieldset><input id="other" /></form>`;
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => vi.useRealTimers());

describe("attend", () => {
  it("scrolls the group of the control into view, flashes it once for a moment and focuses the control", async () => {
    const done = attend("control");
    await vi.advanceTimersByTimeAsync(0);
    expect(await done).toBe(true);
    const group = document.getElementById("g");
    expect((Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>).mock.contexts).toContain(group);
    expect(document.activeElement?.id).toBe("control");
    expect(group?.classList.contains("attend")).toBe(false); // (the tab first, the flash a moment later)
    vi.advanceTimersByTime(PAUSE_MS);
    expect(group?.classList.contains("attend")).toBe(true);
    vi.advanceTimersByTime(ATTEND_MS + 1);
    expect(group?.classList.contains("attend")).toBe(false);
  });

  it("waits for a control that is drawn a moment later, and gives up quietly on one that never is", async () => {
    const late = attend("late");
    await vi.advanceTimersByTimeAsync(100);
    document.getElementById("g")?.insertAdjacentHTML("beforeend", `<div class="field"><input id="late" /></div>`);
    await vi.advanceTimersByTimeAsync(100);
    expect(await late).toBe(true);
    const never = attend("nothing");
    await vi.advanceTimersByTimeAsync(1000);
    expect(await never).toBe(false);
  });

  it("is a soft yellow of the palette that fades in and out quickly, after a short pause", () => {
    expect(cssRule(".attend")).toMatch(/animation:\s*attend 1\.2s/);
    expect([PAUSE_MS, ATTEND_MS]).toEqual([300, 1200]);
  });
});
