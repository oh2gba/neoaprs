// The map's replay: its clock (useReplay) and what it draws, a marker with the APRS symbol and the
// call where each station was at the replay time, with its trail up to there. While on, the live
// markers, tracks and route give way (class `replaying` on the map's root) but stay up to date
// underneath. A span with no positions is said in a toast. `add` is the map's, called each time
// the style is set.
import { onBeforeUnmount, watch } from "vue";
import type { Map as MapLibreMap, Marker } from "maplibre-gl";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useReplay } from "@/composables/useReplay";
import { t } from "@/i18n";
import { buildMarkerDom, paintReplayMarker } from "@/lib/markerdom";
import { placesAt, spanLabel, trailLines } from "@/lib/replay";
import { addReplayLayers, setReplayTrails, showLive } from "@/lib/replaylayers";

interface Engine {
  Marker: new (options: { element: HTMLElement; anchor: "center" }) => Marker;
}

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
        one = {
          marker: new engine.Marker({ element: dom.root, anchor: "center" }).setLngLat([lon, lat]).addTo(map),
          lat,
          lon,
        };
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
    if (data && data.tracks.length === 0) page.say(t("map.replay.none", { span: spanLabel(data.hours) }));
  });
  if (on()) clock.ask();
  onBeforeUnmount(clear);

  return { clock, add };
}
