import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, shallowRef, type EffectScope } from "vue";
import ReplayBar from "@/components/ReplayBar.vue";
import { useReplay } from "@/composables/useReplay";
import { setLocale } from "@/i18n";
import type { Command, PositionHistoryMessage } from "@/protocol/protocol";

const START = "2026-10-21T09:00:00Z";
const T0 = Date.parse(START);
const scopes: EffectScope[] = [];

function setUp() {
  const positionHistory = shallowRef<PositionHistoryMessage | null>(null);
  const send = vi.fn((_command: Command) => true);
  const scope = effectScope();
  scopes.push(scope); // (stopped after the test, with the replay's timer)
  const replay = scope.run(() => useReplay({ send, positionHistory }));
  if (!replay) throw new Error("no replay");
  const wrapper = mount(ReplayBar, { props: { replay }, attachTo: document.body });
  return { replay, send, positionHistory, wrapper };
}

async function answered(positionHistory: { value: PositionHistoryMessage | null }, hours = 3): Promise<void> {
  positionHistory.value = { type: "position_history", hours, start: START, stations: { OH2RDG: [[START, 60, 25]] } };
  await nextTick();
  await nextTick();
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  for (const scope of scopes.splice(0)) scope.stop();
  vi.useRealTimers();
  document.body.replaceChildren();
  setLocale("en");
});

describe("the replay's bar", () => {
  it("waits for the span with its controls off and the clock as dashes, then plays it", async () => {
    const { replay, positionHistory, wrapper } = setUp();
    replay.ask();
    await nextTick();
    expect(wrapper.find(".replaybar").attributes("aria-busy")).toBe("true");
    expect(wrapper.find(".replay-clock").text()).toBe("--:--:--");
    expect(wrapper.find<HTMLButtonElement>(".replay-play").element.disabled).toBe(true);
    expect(wrapper.find<HTMLInputElement>(".replay-slider").element.disabled).toBe(true);
    await answered(positionHistory);
    expect(wrapper.find(".replay-clock").text()).toMatch(/^\d\d:\d\d:\d\d$|^\d\d-\d\d \d\d:\d\d:\d\d$/);
    expect(wrapper.find(".replay-play").attributes("aria-label")).toBe("Pause");
    const slider = wrapper.find<HTMLInputElement>(".replay-slider").element;
    expect([Number(slider.min), Number(slider.max), slider.step]).toEqual([T0, T0 + 3 * 3_600_000, "60000"]);
  });

  it("pauses and plays with its button, seeks with the slider, and changes the speed", async () => {
    const { replay, positionHistory, wrapper } = setUp();
    replay.ask();
    await answered(positionHistory);
    await wrapper.find(".replay-play").trigger("click");
    expect(replay.playing.value).toBe(false);
    expect(wrapper.find(".replay-play").attributes("aria-label")).toBe("Play");
    const slider = wrapper.find<HTMLInputElement>(".replay-slider");
    slider.element.value = String(T0 + 3_600_000);
    await slider.trigger("input");
    expect(replay.at.value).toBe(T0 + 3_600_000);
    const speed = wrapper.find<HTMLSelectElement>(".replay-speed");
    expect([...speed.element.options].map((o) => o.text)).toEqual(["60×", "300×", "900×", "3600×"]);
    await speed.setValue("900");
    expect(replay.speed.value).toBe(900);
  });

  it("asks again for another span, the hours of On map for", async () => {
    const { send, wrapper } = setUp();
    const span = wrapper.find<HTMLSelectElement>(".replay-span");
    expect([...span.element.options].map((o) => o.text)).toEqual(["1 h", "3 h", "6 h", "12 h", "24 h"]);
    await span.setValue("24");
    expect(send).toHaveBeenLastCalledWith({ cmd: "position_history", hours: 24 });
  });

  it("closes with its cross and with Esc, the slider's too, but leaves a select its Esc", async () => {
    const { replay, positionHistory, wrapper } = setUp();
    replay.ask();
    await answered(positionHistory);
    await wrapper.find(".replay-close").trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);
    const esc = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    wrapper.find(".replay-slider").element.dispatchEvent(esc);
    expect(esc.defaultPrevented).toBe(true);
    expect(wrapper.emitted("close")).toHaveLength(2);
    wrapper.find(".replay-speed").element.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(wrapper.emitted("close")).toHaveLength(2);
  });

  it("speaks the page's language", async () => {
    setLocale("de");
    const { wrapper } = setUp();
    await nextTick();
    expect(wrapper.find(".replaybar").attributes("aria-label")).toBe("Wiedergabe der Karte");
    expect(wrapper.find(".replay-span option").text()).toBe("1 Std.");
  });
});
