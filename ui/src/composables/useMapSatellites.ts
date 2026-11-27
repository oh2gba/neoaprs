// The satellites layer of the map: drawn when the daemon tells and a card opens or closes, and moved
// at every step of the map's motion (`mover`) along the points, the open cards' tracks and
// footprints with their marks. A click on a mark opens its card (`clicked`); a click elsewhere on
// the map closes them, as it closes the stations' and the thing's.
import { watch } from "vue";
import type { MapGeoJSONFeature, Map as MapLibreMap } from "maplibre-gl";
import { useDaemonContext } from "@/composables/useDaemonContext";
import type { Mover } from "@/composables/useMapMotion";
import {
  NO_SATELLITES,
  sameMarks,
  satelliteFeatures,
  satelliteMarks,
  type SatelliteFeatures,
} from "@/lib/layers/satellite";
import { easedAt, nextEases, type MarkEase } from "@/lib/layers/satelliteease";
import { SATELLITE_LAYER, addSatelliteLayers, setSatelliteData, setSatelliteMarks } from "@/lib/layers/satellitelayers";

// Pixels each way round a click or tap.
const REACH = 8;

function idOf(feature: MapGeoJSONFeature | undefined): number | null {
  const id: unknown = feature?.properties.id;
  return typeof id === "number" ? id : null;
}

export function useMapSatellites(map: () => MapLibreMap | null) {
  const { satellites } = useDaemonContext();
  // The marks the map was last given, so that a step that moves none sets nothing.
  let shown: SatelliteFeatures["marks"] = NO_SATELLITES.marks;
  let eases = new Map<number, MarkEase>();
  watch(
    satellites.told,
    (now, was) => void (eases = nextEases(was?.satellites ?? [], eases, now?.satellites ?? [], Date.now())),
    { flush: "sync" },
  );
  const place =
    (nowMs: number) =>
    (id: number, at: [number, number]): [number, number] =>
      easedAt(at, eases.get(id), nowMs);
  const features = (nowMs: number): SatelliteFeatures => {
    const told = satellites.told.value;
    return told === null
      ? NO_SATELLITES
      : satelliteFeatures(told.satellites, satellites.cards.value, nowMs, place(nowMs));
  };
  /** Draws the marks at `nowMs`, and the open cards' tracks and footprints from the same places. */
  const show = (to: MapLibreMap, nowMs: number, always: boolean): boolean => {
    const told = satellites.told.value;
    const cards = satellites.cards.value;
    const marks = told === null ? NO_SATELLITES.marks : satelliteMarks(told.satellites, cards, nowMs, place(nowMs));
    if (!always && sameMarks(shown, marks)) return false;
    shown = marks;
    if (always || cards.length > 0) setSatelliteData(to, features(nowMs));
    else setSatelliteMarks(to, marks);
    return true;
  };
  let drawn = false;
  watch([satellites.told, satellites.cards], () => {
    const to = map();
    const on = satellites.told.value !== null;
    if (!to || !(on || drawn)) return;
    show(to, Date.now(), true);
    drawn = on;
  });

  const mover: Mover = {
    active: () => satellites.told.value !== null,
    told: () => [satellites.told.value, satellites.cards.value],
    draw: () => {
      const to = map();
      return to !== null && show(to, Date.now(), false);
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

  return {
    add: (to: MapLibreMap): void => {
      const now = Date.now();
      shown = features(now).marks;
      addSatelliteLayers(to, features(now));
    },
    listen,
    clicked,
    mover,
  };
}
