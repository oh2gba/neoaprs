// The locator grid on the map while its tick is on: its layers are made first with `add`, so it
// lies under everything else, and drawn again for the visible part when the view stops moving.
import { watch } from "vue";
import type { Map as MapLibreMap } from "maplibre-gl";
import { NO_GRID, gridFeatures, type GridCollection } from "@/lib/layers/grid";
import { addGridLayers, setGridData } from "@/lib/layers/gridlayers";

export function useMapGrid(
  map: () => MapLibreMap | null,
  on: () => boolean,
): { add: (to: MapLibreMap) => void; listen: (to: MapLibreMap) => void } {
  function data(of: MapLibreMap): GridCollection {
    if (!on()) return NO_GRID;
    const view = of.getBounds();
    return gridFeatures({
      west: view.getWest(),
      south: view.getSouth(),
      east: view.getEast(),
      north: view.getNorth(),
      zoom: of.getZoom(),
    });
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
