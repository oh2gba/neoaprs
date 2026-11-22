import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";
import type { Map as MapLibreMap } from "maplibre-gl";
import { useMapDayNight } from "@/composables/useMapDayNight";
import { NO_DAYNIGHT, dayNightFeatures } from "@/lib/layers/daynight";
import { fakeDaemon, withDaemon } from "@/test/context";

const MINUTE = 60000;
const START = Date.UTC(2026, 5, 21, 12, 0, 10);

function setup(ticked: boolean) {
  const setData = vi.fn();
  const sources: string[] = [];
  const map = {
    getSource: (id: string) => {
      sources.push(id);
      return { setData };
    },
  } as unknown as MapLibreMap;
  const on = ref(ticked);
  const daemon = fakeDaemon({ now: START });
  const Probe = defineComponent({
    setup() {
      useMapDayNight(
        () => map,
        () => on.value,
      );
      return () => h("div");
    },
  });
  const wrapper = mount(Probe, { global: withDaemon(daemon) });
  return { on, daemon, setData, sources, wrapper };
}

describe("the Day and night shade", () => {
  it("draws nothing while the tick is off", async () => {
    const { on, setData } = setup(true);
    on.value = false;
    await nextTick();
    expect(setData).toHaveBeenLastCalledWith(NO_DAYNIGHT);
  });

  it("draws the twilight and the night for the page's clock when ticked", async () => {
    const { on, setData } = setup(false);
    on.value = true;
    await nextTick();
    expect(setData).toHaveBeenLastCalledWith(dayNightFeatures(START));
  });

  it("sets nothing for a change of the clock within the minute, and the source of its own for a new minute", async () => {
    const { daemon, setData, sources } = setup(true);
    daemon.now.value = START + 20000;
    await nextTick();
    expect(setData).not.toHaveBeenCalled();
    daemon.now.value = START - 10000 + MINUTE;
    await nextTick();
    expect(setData).toHaveBeenCalledTimes(1);
    expect(setData).toHaveBeenLastCalledWith(dayNightFeatures(START - 10000 + MINUTE));
    expect(new Set(sources)).toEqual(new Set(["daynight"]));
  });
});
