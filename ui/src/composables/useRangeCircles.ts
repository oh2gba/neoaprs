// The range circle of the selected station on the map, when it is a digipeater of the Nearby tab that gave a range: the layers made with the others, the circle drawn again when the selection or the station's row changes (and gone with the selection).
import { watch } from "vue";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { rangeCircleOf } from "@/lib/nearby";
import { rangeFeatures } from "@/lib/rangecircles";
import { RANGE_SOURCE, addRangeLayers } from "@/lib/rangelayers";

export function useRangeCircles(map: () => MapLibreMap | null, selected: () => string | null): { add: (on: MapLibreMap) => void } {
  const page = useDaemonContext();
  const circle = () => rangeCircleOf(page.stations.value.values(), selected());
  const features = () => {
    const one = circle();
    return rangeFeatures(one === null ? [] : [one]);
  };

  let drawn = "";
  /** Sets the data of the source, unless the circle is the one already there (the rows are told again for every packet). */
  function draw(): void {
    const data = features();
    const key = JSON.stringify(data);
    if (key === drawn) return;
    drawn = key;
    void map()?.getSource<GeoJSONSource>(RANGE_SOURCE)?.setData(data);
  }
  watch([selected, () => [...page.stations.value.values()]], draw);
  return {
    add: (on) => {
      const data = features();
      drawn = JSON.stringify(data);
      addRangeLayers(on, data);
    },
  };
}
