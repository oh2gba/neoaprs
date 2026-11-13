import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, ref, shallowRef } from "vue";
import { ASK_EVERY_MS, useSkeds } from "@/composables/useSkeds";
import { usePanel } from "@/composables/usePanel";
import type { Command, SkedRow, SkedsState } from "@/protocol/protocol";
import { sked, skedsState } from "@/test/fixtures";

/** The composable inside a component, with the panel as `usePanel` makes it; `show` is the tab in front before it is made. */
function setUp(rows: SkedRow[], show?: "skeds" | "stations", collapsed = false, connected = true) {
  const topic = shallowRef<SkedsState | null>(skedsState(rows));
  const live = ref(connected);
  const send = vi.fn((_command: Command) => true);
  let made: { panel: ReturnType<typeof usePanel>; fresh: ReturnType<typeof useSkeds>["fresh"] } | undefined;
  const wrapper = mount(
    defineComponent({
      setup() {
        const panel = usePanel();
        if (show) panel.show(show);
        panel.collapsed.value = collapsed;
        made = { panel, fresh: useSkeds(topic, panel, send, live).fresh };
        return () => h("div");
      },
    }),
  );
  if (made === undefined) throw new Error("not set up");
  return { ...made, topic, send, wrapper, live };
}
const wanted = (send: ReturnType<typeof setUp>["send"]) => send.mock.calls.filter(([command]) => command.cmd === "skeds_wanted").length;

beforeEach(() => localStorage.clear());
afterEach(() => vi.useRealTimers());

describe("useSkeds: the count", () => {
  it("counts every sked of others as new until the tab has been on show, and none after; ours are never new", async () => {
    const { panel, fresh } = setUp([sked("a"), sked("b"), sked("c", { ours: true })], "stations");
    expect(fresh.value).toBe(2);
    panel.show("skeds");
    await nextTick();
    expect(fresh.value).toBe(0);
    expect(JSON.parse(localStorage.getItem("NeoAPRS.skedsseen") ?? "[]")).toEqual(["a", "b", "c"]);
  });

  it("counts a sked that comes while another tab is on show, and not one that comes while the board is looked at", async () => {
    const { panel, fresh, topic } = setUp([sked("a")], "skeds");
    expect(fresh.value).toBe(0);
    topic.value = skedsState([sked("a"), sked("b")]);
    await nextTick();
    expect(fresh.value).toBe(0);
    panel.show("stations");
    topic.value = skedsState([sked("a"), sked("b"), sked("c")]);
    await nextTick();
    expect(fresh.value).toBe(1);
    topic.value = skedsState([sked("a"), sked("b"), sked("c"), sked("d")]);
    await nextTick();
    expect(fresh.value).toBe(2);
    panel.show("skeds");
    await nextTick();
    expect(fresh.value).toBe(0);
  });

  it("does not take them as seen while the panel is folded away, though the Skeds tab is the tab", async () => {
    const { fresh, topic } = setUp([], "skeds", true);
    topic.value = skedsState([sked("a")]);
    await nextTick();
    expect(fresh.value).toBe(1);
  });

  it("remembers what was seen across page loads, and counts none before the daemon has told", async () => {
    setUp([sked("a")], "skeds");
    await nextTick();
    expect(setUp([sked("a"), sked("b")], "stations").fresh.value).toBe(1);
    const topic = shallowRef<SkedsState | null>(null);
    let fresh = -1;
    mount(
      defineComponent({
        setup() {
          const result = useSkeds(topic, usePanel(), () => true, ref(true));
          return () => h("div", (fresh = result.fresh.value));
        },
      }),
    );
    expect(fresh).toBe(0);
  });

  it("starts again from nothing seen when what the browser kept is not a list of ids", () => {
    localStorage.setItem("NeoAPRS.skedsseen", "{not json");
    expect(setUp([sked("a")], "stations").fresh.value).toBe(1);
    localStorage.setItem("NeoAPRS.skedsseen", JSON.stringify({ a: 1 }));
    expect(setUp([sked("a")], "stations").fresh.value).toBe(1);
    localStorage.setItem("NeoAPRS.skedsseen", JSON.stringify(["a", 5, null]));
    expect(setUp([sked("a"), sked("b")], "stations").fresh.value).toBe(1);
  });

  it("keeps the last 200 ids", async () => {
    const rows = Array.from({ length: 100 }, (_, i) => sked(`a${i}`));
    const { topic, panel } = setUp(rows, "stations");
    panel.show("skeds");
    await nextTick();
    topic.value = skedsState(Array.from({ length: 100 }, (_, i) => sked(`b${i}`)));
    await nextTick();
    topic.value = skedsState(Array.from({ length: 100 }, (_, i) => sked(`c${i}`)));
    await nextTick();
    const kept = JSON.parse(localStorage.getItem("NeoAPRS.skedsseen") ?? "[]") as string[];
    expect(kept).toHaveLength(200);
    expect(kept).not.toContain("a0");
    expect(kept).toContain("c99");
  });
});

describe("useSkeds: asking the daemon for the board", () => {
  it("asks when the tab comes on show, once, and not while another tab is in front", async () => {
    const { panel, send } = setUp([], "stations");
    expect(wanted(send)).toBe(0);
    panel.show("skeds");
    await nextTick();
    expect(wanted(send)).toBe(1);
    await nextTick();
    expect(wanted(send)).toBe(1);
  });

  it("asks at once where the tab is the tab already", () => {
    expect(wanted(setUp([], "skeds").send)).toBe(1);
  });

  it("asks once the socket is open when the page loads with the tab in front, and again after a reconnect", async () => {
    vi.useFakeTimers();
    const { send, live } = setUp([], "skeds", false, false);
    expect(wanted(send)).toBe(0);
    live.value = true;
    await nextTick();
    expect(wanted(send)).toBe(1);
    live.value = false;
    await nextTick();
    vi.advanceTimersByTime(2 * ASK_EVERY_MS);
    expect(wanted(send)).toBe(1);
    live.value = true;
    await nextTick();
    expect(wanted(send)).toBe(2);
  });

  it("asks again every 15 minutes while it stays on show, and stops when it leaves", async () => {
    vi.useFakeTimers();
    const { panel, send } = setUp([], "skeds");
    expect(wanted(send)).toBe(1);
    vi.advanceTimersByTime(ASK_EVERY_MS - 1);
    expect(wanted(send)).toBe(1);
    vi.advanceTimersByTime(1);
    expect(wanted(send)).toBe(2);
    vi.advanceTimersByTime(ASK_EVERY_MS);
    expect(wanted(send)).toBe(3);
    panel.show("stations");
    await nextTick();
    vi.advanceTimersByTime(3 * ASK_EVERY_MS);
    expect(wanted(send)).toBe(3);
  });

  it("does not ask while the panel is folded away, and asks when it is opened", async () => {
    const { panel, send } = setUp([], "skeds", true);
    expect(wanted(send)).toBe(0);
    panel.collapsed.value = false;
    await nextTick();
    expect(wanted(send)).toBe(1);
  });

  it("stops asking when the page is gone", () => {
    vi.useFakeTimers();
    const { wrapper, send } = setUp([], "skeds");
    wrapper.unmount();
    vi.advanceTimersByTime(2 * ASK_EVERY_MS);
    expect(wanted(send)).toBe(1);
  });
});
