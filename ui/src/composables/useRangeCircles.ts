// The range circles of the digipeaters on the map, when the Nearby tab's "Show range" is on: the layers made with the others, the circles drawn again when the stations, the time (a minute at a time: a station times out) or the choice change.
import { computed, watch, type Ref } from "vue";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { timedOut } from "@/lib/aging";
import { digipeaters, rangeCircles } from "@/lib/nearby";
import { rangeFeatures } from "@/lib/rangecircles";
import { RANGE_SOURCE, addRangeLayers } from "@/lib/rangelayers";

export function useRangeCircles(map: () => MapLibreMap | null, show: Readonly<Ref<boolean>>): { add: (on: MapLibreMap) => void } {
  const page = useDaemonContext();
  const minute = computed(() => Math.floor(page.now.value / 60_000));
  const circles = () => (show.value ? rangeCircles(digipeaters(page.stations.value.values()), (row) => timedOut(page.aging.value, row, page.now.value)) : []);
  const features = () => rangeFeatures(circles());

  let drawn = "";
  /** Sets the data of the source, unless the circles are the ones already there (the rows are told again for every packet). */
  function draw(): void {
    const data = features();
    const key = JSON.stringify(data);
    if (key === drawn) return;
    drawn = key;
    void map()?.getSource<GeoJSONSource>(RANGE_SOURCE)?.setData(data);
  }
  watch([show, minute, () => [...page.stations.value.values()]], draw);
  return {
    add: (on) => {
      const data = features();
      drawn = JSON.stringify(data);
      addRangeLayers(on, data);
    },
  };
}
