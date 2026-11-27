// What the map's Layers box switches on: the box's place under the zoom buttons (`listen`,
// `place`), and the layers drawn under its ticks. `add` makes the day and night shade and the
// locator grid first, so that they lie under everything, then the circles, the aircraft and
// ships, and the satellites over them; a click is a satellite's before a thing's. `tracks` says whether
// every track is drawn or only the open cards' own.
import { ref } from "vue";
import type { Map as MapLibreMap } from "maplibre-gl";
import { useMapCircles } from "@/composables/useMapCircles";
import { useMapDayNight } from "@/composables/useMapDayNight";
import { useMapGrid } from "@/composables/useMapGrid";
import { useMapLayers } from "@/composables/useMapLayers";
import { useMapSatellites } from "@/composables/useMapSatellites";
import { useMapTraffic } from "@/composables/useMapTraffic";
import type { HoverCard } from "@/lib/hovercard";
import { layersControl } from "@/lib/layers/control";

export function useMapBoxLayers(map: () => MapLibreMap | null, selected: () => string | null) {
  const layers = useMapLayers();
  const daynight = useMapDayNight(map, () => layers.ticked("daynight"));
  const grid = useMapGrid(map, () => layers.ticked("grid"));
  const circles = useMapCircles(map, selected, () => layers.ticked("aloha"));
  const traffic = useMapTraffic(map);
  const satellites = useMapSatellites(map);
  const place = ref<HTMLElement | null>(null);
  return {
    place,
    tracks: (): boolean => layers.ticked("tracks"),
    clicked: (event?: { point?: { x: number; y: number } }): boolean =>
      satellites.clicked(event) || traffic.clicked(event),
    counts: traffic.counts,
    credits: traffic.credits,
    shapes: traffic.shapes,
    add: (to: MapLibreMap): void => {
      daynight.add(to);
      grid.add(to);
      circles.add(to);
      traffic.add(to);
      satellites.add(to);
    },
    listen: (to: MapLibreMap, hover: HoverCard | null = null): void => {
      to.addControl(layersControl(place), "top-left");
      grid.listen(to);
      traffic.listen(to, hover);
      satellites.listen(to);
    },
  };
}
