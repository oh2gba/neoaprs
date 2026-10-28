// The map's replay as the map runs it (components/StationMap.vue; opened from the map's menu, Replay, and closed by the bar's cross or Esc, which the page decides: `on`): its clock (composables/useReplay.ts), and
// what it draws, a marker with the APRS symbol and the call where each station was at the time of the replay and its trail up to there (lib/replay.ts, lib/replaylayers.ts). While it is on, the live markers give
// way (the class `replaying` of the map's box hides them, styles/map.css) and so do the live tracks and the route; they go on being kept up to date underneath, so that closing the replay brings the live map back
// as it is. A span with no positions in it is said in the toast. `add` is the map's, with its other layers, each time the style is set.
import { onBeforeUnmount, watch } from "vue";
import type { Map as MapLibreMap, Marker } from "maplibre-gl";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useReplay } from "@/composables/useReplay";
import { t } from "@/i18n";
import { buildMarkerDom, paintReplayMarker } from "@/lib/markerdom";
import { placesAt, trailLines } from "@/lib/replay";
import { addReplayLayers, setReplayTrails, showLive } from "@/lib/replaylayers";

interface Engine {
  Marker: new (options: { element: HTMLElement; anchor: "center" }) => Marker;
}

/** What the map lends the replay: the map, and the engine its markers are made with (null until they are there), and whether the replay is open (the page's). */
interface ReplayParts {
  map: MapLibreMap | null;
  engine: Engine | null;
  open: boolean;
}

export function useMapReplay(parts: () => ReplayParts) {
  const on = (): boolean => parts().open;
  const page = useDaemonContext();
  const clock = useReplay(page);
  const markers = new Map<string, { marker: Marker; lat: number; lon: number }>();

  function clear(): void {
    for (const one of markers.values()) one.marker.remove();
    markers.clear();
  }

  function draw(): void {
    const { map, engine } = parts();
    const data = clock.data.value;
    if (!map || !engine || !on() || !data) {
      clear();
      if (map) setReplayTrails(map);
      return;
    }
    const time = clock.at.value;
    setReplayTrails(map, trailLines(data, time));
    const present = new Set<string>();
    for (const [call, lat, lon] of placesAt(data, time)) {
      present.add(call);
      let one = markers.get(call);
      if (!one) {
        const dom = buildMarkerDom();
        paintReplayMarker(dom, call, page.stations.value.get(call));
        one = { marker: new engine.Marker({ element: dom.root, anchor: "center" }).setLngLat([lon, lat]).addTo(map), lat, lon };
        markers.set(call, one);
      } else if (one.lat !== lat || one.lon !== lon) {
        one.marker.setLngLat([lon, lat]);
        Object.assign(one, { lat, lon });
      }
    }
    for (const [call, one] of markers) {
      if (present.has(call)) continue;
      one.marker.remove();
      markers.delete(call);
    }
  }

  /** The layers of the replay, made with the map's others; the live ones give way at once when the replay is on. */
  function add(): void {
    const { map } = parts();
    if (!map) return;
    addReplayLayers(map);
    showLive(map, !on());
    draw();
  }

  watch(on, (open) => {
    if (open) clock.ask();
    else clock.stop();
    const { map } = parts();
    if (map) showLive(map, !open);
    draw();
  });
  watch([clock.at, clock.data], draw);
  watch(clock.data, (data) => {
    if (data && data.tracks.length === 0) page.say(t("map.replay.none", { hours: data.hours }));
  });
  if (on()) clock.ask(); // (the page was opened with the replay on)
  onBeforeUnmount(clear);

  return { clock, add };
}
