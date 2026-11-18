// The locator grid on the map while its tick is on (composables/useMapLayers.ts): its layers made with the others (`add`, first, so that the grid lies under everything else), and drawn again for the part of the
// map in view when the view stops moving (`listen`) and when the tick changes; with the tick off it draws nothing.
import { watch } from "vue";
import type { Map as MapLibreMap } from "maplibre-gl";
import { NO_GRID, gridFeatures, type GridCollection } from "@/lib/layers/grid";
import { addGridLayers, setGridData } from "@/lib/layers/gridlayers";

export function useMapGrid(map: () => MapLibreMap | null, on: () => boolean): { add: (to: MapLibreMap) => void; listen: (to: MapLibreMap) => void } {
  function data(of: MapLibreMap): GridCollection {
    if (!on()) return NO_GRID;
    const view = of.getBounds();
    return gridFeatures({ west: view.getWest(), south: view.getSouth(), east: view.getEast(), north: view.getNorth(), zoom: of.getZoom() });
  }
  function draw(): void {
    const now = map();
    if (now) setGridData(now, data(now));
  }
  watch(on, draw);
  return {
    add: (to) => addGridLayers(to, data(to)),
    listen: (to) => void to.on("moveend", draw),
  };
}
