// The circles under the markers: the ALOHA circle round our station while its Layers row is
// ticked (`aloha`) and the range circle of the selected digipeater with a range. `add` makes the
// layers, the ALOHA circle first so the range lies over it.
import type { Map as MapLibreMap } from "maplibre-gl";
import { useAlohaCircle } from "@/composables/useAlohaCircle";
import { useRangeCircles } from "@/composables/useRangeCircles";

export function useMapCircles(
  map: () => MapLibreMap | null,
  selected: () => string | null,
  aloha: () => boolean,
): { add: (on: MapLibreMap) => void } {
  const circle = useAlohaCircle(map, aloha);
  const range = useRangeCircles(map, selected);
  return {
    add: (on) => {
      circle.add(on);
      range.add(on);
    },
  };
}
