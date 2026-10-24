import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, ref, shallowRef } from "vue";
import { useStationCards } from "@/composables/useStationCards";
import type { Layout } from "@/composables/useLayout";
import type { Command, StationRow } from "@/protocol/protocol";
import { station } from "@/test/fixtures";

const KEY = "NeoAPRS.pinnedcards";
const CALLS = ["OH2ZWA", "OH2ZWB", "OH2ZWC"];

const mounted: VueWrapper[] = [];

function setUp(stored?: unknown, told = true) {
  if (stored !== undefined) localStorage.setItem(KEY, JSON.stringify(stored));
  const stations = shallowRef<ReadonlyMap<string, StationRow>>(told ? new Map(CALLS.map((call) => [call, station(call)] as const)) : new Map());
  const ready = ref(told);
  const layout = { capacity: ref(4), phone: ref(false), showMap: vi.fn() } as unknown as Layout;
  let cards!: ReturnType<typeof useStationCards>;
  const wrapper = mount(
    defineComponent({
      setup() {
        cards = useStationCards(
          stations,
          vi.fn((_command: Command) => true),
          layout,
          () => false,
          ready,
        );
        return () => h("div");
      },
    }),
    { attachTo: document.body },
  );
  mounted.push(wrapper);
  return { cards, stations, ready, layout, wrapper };
}

const escape = () => document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
const stored = (): Record<string, unknown> => JSON.parse(localStorage.getItem(KEY) ?? "null") as Record<string, unknown>;

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  document.body.replaceChildren();
  localStorage.clear();
});

describe("useStationCards: pinned cards", () => {
  it("keeps a pinned card past Esc, and closes the others", async () => {
    const { cards } = setUp();
    cards.pick("OH2ZWA");
    cards.pick("OH2ZWB", true);
    cards.pin("OH2ZWA", true);
    escape();
    await nextTick();
    expect(cards.open.value).toEqual(["OH2ZWA"]);
  });

  it("keeps a pinned card past a click on the map and Close all", () => {
    const { cards } = setUp();
    cards.pick("OH2ZWA");
    cards.pin("OH2ZWA", true);
    cards.onMarker(null);
    cards.closeAll();
    expect(cards.open.value).toEqual(["OH2ZWA"]);
    cards.onMarker("OH2ZWB");
    expect(cards.open.value).toEqual(["OH2ZWA", "OH2ZWB"]);
  });

  it("does not take Esc when only pinned cards are open", () => {
    const { cards } = setUp();
    cards.pick("OH2ZWA");
    cards.pin("OH2ZWA", true);
    const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    document.body.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });

  it("remembers the pinned calls and their places in this browser, and forgets them when the cross is clicked", async () => {
    const { cards } = setUp();
    cards.pick("OH2ZWA");
    cards.pick("OH2ZWB", true);
    cards.places.value = { OH2ZWA: { x: 20, y: 300 }, OH2ZWB: { x: 400, y: 10 } };
    cards.pin("OH2ZWA", true);
    cards.pin("OH2ZWB", true);
    await nextTick();
    expect(stored()).toEqual({ OH2ZWA: { x: 20, y: 300 }, OH2ZWB: { x: 400, y: 10 } });
    cards.places.value = { OH2ZWA: { x: 25, y: 310 }, OH2ZWB: { x: 400, y: 10 } };
    await nextTick();
    expect(stored()["OH2ZWA"]).toEqual({ x: 25, y: 310 });
    cards.close("OH2ZWA");
    await nextTick();
    expect(Object.keys(stored())).toEqual(["OH2ZWB"]);
    cards.pin("OH2ZWB", false);
    await nextTick();
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it("brings the pinned cards back after a reload, in their places, once the daemon has told the stations", async () => {
    const { cards, stations, ready } = setUp({ OH2ZWC: { x: 5, y: 6 }, OH2ZWA: null, OH2ZWX: { x: 1, y: 1 } }, false);
    expect(cards.open.value).toEqual([]);
    expect(cards.places.value).toEqual({ OH2ZWC: { x: 5, y: 6 }, OH2ZWX: { x: 1, y: 1 } });
    stations.value = new Map(CALLS.map((call) => [call, station(call)] as const));
    ready.value = true;
    await nextTick();
    expect(cards.open.value).toEqual(["OH2ZWC", "OH2ZWA"]);
    expect(cards.pinned.value).toEqual(["OH2ZWC", "OH2ZWA"]);
    expect(cards.rows.value.map((row) => row.call)).toEqual(["OH2ZWC", "OH2ZWA"]);
    await nextTick();
    expect(Object.keys(stored())).toEqual(["OH2ZWC", "OH2ZWA"]);
  });

  it("starts with no card when nothing was stored or what was stored is not usable", () => {
    expect(setUp().cards.open.value).toEqual([]);
    localStorage.setItem(KEY, "{{");
    expect(setUp().cards.open.value).toEqual([]);
  });

  it("does not open the pinned cards on a phone, whose card is a sheet, and opens them when the window is wide again", async () => {
    localStorage.setItem(KEY, JSON.stringify({ OH2ZWA: null }));
    const stations = shallowRef<ReadonlyMap<string, StationRow>>(new Map(CALLS.map((call) => [call, station(call)] as const)));
    const layout = { capacity: ref(1), phone: ref(true), showMap: vi.fn() } as unknown as Layout;
    let cards!: ReturnType<typeof useStationCards>;
    mounted.push(
      mount(
        defineComponent({
          setup() {
            cards = useStationCards(
              stations,
              vi.fn(() => true),
              layout,
              () => false,
              ref(true),
            );
            return () => h("div");
          },
        }),
      ),
    );
    await nextTick();
    expect(cards.open.value).toEqual([]);
    (layout.phone as unknown as { value: boolean }).value = false;
    await nextTick();
    expect(cards.open.value).toEqual(["OH2ZWA"]);
  });
});
