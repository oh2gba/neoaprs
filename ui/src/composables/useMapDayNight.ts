// The Day and night shade on the map while it is shown and ticked: its layers are made with `add`
// and its data drawn again whenever the tick changes or the page's clock reaches a new minute.
import { watch } from "vue";
import type { Map as MapLibreMap } from "maplibre-gl";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { NO_DAYNIGHT, dayNightFeatures, type DayNightCollection } from "@/lib/layers/daynight";
import { addDayNightLayers, setDayNightData } from "@/lib/layers/daynightlayers";

const MINUTE_MS = 60000;

export function useMapDayNight(map: () => MapLibreMap | null, on: () => boolean): { add: (to: MapLibreMap) => void } {
  const page = useDaemonContext();
  const data = (): DayNightCollection => (on() ? dayNightFeatures(page.now.value) : NO_DAYNIGHT);
  watch([on, () => Math.floor(page.now.value / MINUTE_MS)], () => {
    const now = map();
    if (now) setDayNightData(now, data());
  });
  return { add: (to) => addDayNightLayers(to, data()) };
}
