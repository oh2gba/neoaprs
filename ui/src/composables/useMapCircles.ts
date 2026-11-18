// The circles under the markers of the map: the ALOHA circle round our own station, while its row of the Layers box is ticked (`aloha`), and the range circle of the selected station, when it is a digipeater that
// gave a range (composables/useAlohaCircle.ts, composables/useRangeCircles.ts). `add` makes the layers (the ALOHA circle first, so the range is over it).
import type { Map as MapLibreMap } from "maplibre-gl";
import { useAlohaCircle } from "@/composables/useAlohaCircle";
import { useRangeCircles } from "@/composables/useRangeCircles";

export function useMapCircles(map: () => MapLibreMap | null, selected: () => string | null, aloha: () => boolean): { add: (on: MapLibreMap) => void } {
  const circle = useAlohaCircle(map, aloha);
  const range = useRangeCircles(map, selected);
  return {
    add: (on) => {
      circle.add(on);
      range.add(on);
    },
  };
}
