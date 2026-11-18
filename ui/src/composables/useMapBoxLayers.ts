// What the map's Layers box switches on the map of the stations, made with the map: the box's place under the zoom buttons (`listen` adds it to the map's controls: lib/layers/control.ts, `place` for
// components/MapLayers.vue), and the layers the station and the page draw themselves under their ticks (composables/useMapLayers.ts): `add` makes the locator grid first, so that it lies under everything,
// then the circles (the ALOHA circle while it is ticked, the range of the selected digipeater: composables/useMapCircles.ts), then the aircraft and ships (composables/useMapTraffic.ts: `clicked`, `counts`,
// `credits` and `shapes` are theirs); `tracks` says whether every track is drawn or only the open cards' own.
import { ref } from "vue";
import type { Map as MapLibreMap } from "maplibre-gl";
import { useMapCircles } from "@/composables/useMapCircles";
import { useMapGrid } from "@/composables/useMapGrid";
import { useMapLayers } from "@/composables/useMapLayers";
import { useMapTraffic } from "@/composables/useMapTraffic";
import type { HoverCard } from "@/lib/hovercard";
import { layersControl } from "@/lib/layers/control";

export function useMapBoxLayers(map: () => MapLibreMap | null, selected: () => string | null) {
  const layers = useMapLayers();
  const grid = useMapGrid(map, () => layers.ticked("grid"));
  const circles = useMapCircles(map, selected, () => layers.ticked("aloha"));
  const traffic = useMapTraffic(map);
  const place = ref<HTMLElement | null>(null);
  return {
    place,
    tracks: (): boolean => layers.ticked("tracks"),
    clicked: traffic.clicked,
    counts: traffic.counts,
    credits: traffic.credits,
    shapes: traffic.shapes,
    add: (to: MapLibreMap): void => {
      grid.add(to);
      circles.add(to);
      traffic.add(to);
    },
    /** `hover`: the map's hover box, which shows the aircraft and ships too */
    listen: (to: MapLibreMap, hover: HoverCard | null = null): void => {
      to.addControl(layersControl(place), "top-left");
      grid.listen(to);
      traffic.listen(to, hover);
    },
  };
}
