// The satellites layer of the map: drawn again at every second of the layer's own clock and when the
// daemon tells; between those the map's motion (`mover`) moves the marks along their points. A click on a mark opens its card (`clicked`);
// a click elsewhere on the map closes them, as it closes the stations' and the thing's.
import { watch } from "vue";
import type { MapGeoJSONFeature, Map as MapLibreMap } from "maplibre-gl";
import { useDaemonContext } from "@/composables/useDaemonContext";
import type { Mover } from "@/composables/useMapMotion";
import { NO_SATELLITES, satelliteFeatures, satelliteMarks, type SatelliteFeatures } from "@/lib/layers/satellite";
import { SATELLITE_LAYER, addSatelliteLayers, setSatelliteData, setSatelliteMarks } from "@/lib/layers/satellitelayers";

// Pixels each way round a click or tap.
const REACH = 8;

function idOf(feature: MapGeoJSONFeature | undefined): number | null {
  const id: unknown = feature?.properties.id;
  return typeof id === "number" ? id : null;
}

export function useMapSatellites(map: () => MapLibreMap | null) {
  const { satellites } = useDaemonContext();
  const features = (): SatelliteFeatures => {
    const told = satellites.told.value;
    return told === null
      ? NO_SATELLITES
      : satelliteFeatures(told.satellites, satellites.cards.value, satellites.now.value);
  };
  let drawn = false;
  watch([satellites.told, satellites.cards, satellites.now], () => {
    const to = map();
    const shown = satellites.told.value !== null;
    if (!to || !(shown || drawn)) return;
    setSatelliteData(to, features());
    drawn = shown;
  });

  const mover: Mover = {
    active: () => satellites.told.value !== null,
    draw: (nowMs) => {
      const to = map();
      const told = satellites.told.value;
      if (to && told) setSatelliteMarks(to, satelliteMarks(told.satellites, satellites.cards.value, nowMs));
    },
  };

  function listen(to: MapLibreMap): void {
    to.on("mouseenter", SATELLITE_LAYER, () => (to.getCanvas().style.cursor = "pointer"));
    to.on("mouseleave", SATELLITE_LAYER, () => (to.getCanvas().style.cursor = ""));
  }

  /** A click on the map: true if it opened a satellite's card, false if it closed them. */
  function clicked(event?: { point?: { x: number; y: number } }): boolean {
    const to = map();
    const point = event?.point;
    const hit =
      to && point && to.getLayer(SATELLITE_LAYER)
        ? idOf(
            to.queryRenderedFeatures(
              [
                [point.x - REACH, point.y - REACH],
                [point.x + REACH, point.y + REACH],
              ],
              { layers: [SATELLITE_LAYER] },
            )[0],
          )
        : null;
    if (hit === null) {
      satellites.closeAll();
      return false;
    }
    satellites.open(hit);
    return true;
  }

  return { add: (to: MapLibreMap): void => addSatelliteLayers(to, features()), listen, clicked, mover };
}
