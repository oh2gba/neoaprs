// The aircraft and ships on the map of the stations (composables/useLayerThings.ts has the tables of the layers this page looks at): the map's layer of them (lib/layers/trafficlayers.ts), drawn again when a table
// comes and as the clock moves on (they fade and are dropped by their age); a mouse resting on one shows the page's hover box (lib/hovercard.ts, its rows lib/layers/card.ts), a click on one opens its card and a
// click elsewhere on the map closes it (`clicked`, which the map asks first); how many each layer draws (`counts`, for the Layers box), the credits of the services drawn (`credits`, for the map's (i)) and whether
// the aircraft are drawn (`shapes`: the (i) names where their shapes are from then).
import { computed, watch } from "vue";
import type { MapGeoJSONFeature, MapLayerMouseEvent, Map as MapLibreMap } from "maplibre-gl";
import { useDaemonContext } from "@/composables/useDaemonContext";
import type { HoverCard, HoverContent } from "@/lib/hovercard";
import { hoverRows, thingSub, thingTitle } from "@/lib/layers/card";
import { isService, type LayerName, type ServiceName } from "@/lib/layers/sources";
import { MARKS, markBox } from "@/lib/layers/marks";
import { kindShape, liveThings, trafficCounts, trafficFeatures } from "@/lib/layers/traffic";
import { NO_TRAIL, trailKey, trailLines } from "@/lib/layers/trail";
import type { TrackCollection } from "@/lib/tracks";
import { TRAFFIC_LAYER, addTrafficLayers, setTrafficData, setTrailData } from "@/lib/layers/trafficlayers";

const HALF = 8; // half a mark, in pixels: the box the hover card stands beside
const REACH = 6; // in pixels each way round a click or a tap: a finger finds a mark it nearly touched (the topmost found is the one meant)

/** The box round a point of the map that a click reaches. */
const reach = (point: { x: number; y: number }): [[number, number], [number, number]] => [
  [point.x - REACH, point.y - REACH],
  [point.x + REACH, point.y + REACH],
];

/** The layer and id of a thing the map drew, from its feature's properties. */
function thingOf(feature: MapGeoJSONFeature | undefined): { layer: LayerName; id: string } | null {
  const layer: unknown = feature?.properties.layer;
  const id: unknown = feature?.properties.id;
  return (layer === "aircraft" || layer === "ships") && typeof id === "string" ? { layer, id } : null;
}

/** The way the thing whose card is open has gone, on the map (nothing without a card): one update when a table comes or the card changes, and none while there is no trail on the map and none is to come. Gives the lines now. */
function useOpenTrail(map: () => MapLibreMap | null): () => TrackCollection {
  const page = useDaemonContext();
  const traffic = page.traffic;
  const lines = (): TrackCollection => {
    const open = traffic.card.value;
    return open ? trailLines(trailKey(open.layer, open.thing.id), traffic.trail.value, page.now.value) : NO_TRAIL;
  };
  const openKey = computed(() => (traffic.card.value ? trailKey(traffic.card.value.layer, traffic.card.value.thing.id) : null));
  let drawn = false;
  watch([traffic.trail, openKey], () => {
    const to = map();
    const open = openKey.value !== null;
    if (!to || !(open || drawn)) return;
    setTrailData(to, lines());
    drawn = open;
  });
  return lines;
}

export function useMapTraffic(map: () => MapLibreMap | null) {
  const page = useDaemonContext();
  let hover: HoverCard | null = null; // (the map's, given with `listen`)
  const traffic = page.traffic;
  const draw = (): void => {
    const to = map();
    if (to) setTrafficData(to, trafficFeatures(traffic.tables.value.values(), page.now.value));
  };
  watch([traffic.tables, page.now], draw);
  const trail = useOpenTrail(map);

  /** What the hover box says of a thing as it is now; null when it has gone. */
  function content(layer: LayerName, id: string): HoverContent | null {
    const table = traffic.tables.value.get(layer);
    const thing = table ? liveThings(table, page.now.value).find((one) => one.id === id) : undefined;
    if (!thing) return null;
    const mark = MARKS[kindShape(layer, thing)];
    return {
      title: thingTitle(layer, thing),
      sub: thingSub(layer),
      rows: hoverRows(layer, thing, page.now.value),
      mark: { d: mark.d, viewBox: markBox(mark), bad: thing.emergency },
    };
  }

  /** Where a thing is on the screen: the box of its mark round its place now. */
  function boxOf(to: MapLibreMap, layer: LayerName, id: string): DOMRect {
    const thing = traffic.tables.value.get(layer)?.things.find((one) => one.id === id);
    const frame = to.getContainer().getBoundingClientRect();
    const at = thing ? to.project([thing.lon, thing.lat]) : { x: 0, y: 0 };
    return new DOMRect(frame.left + at.x - HALF, frame.top + at.y - HALF, 2 * HALF, 2 * HALF);
  }

  function listen(to: MapLibreMap, card: HoverCard | null): void {
    hover = card;
    let mouse = false; // (the pointer is a mouse: a touch shows no hover box, a tap opens the card)
    to.getContainer().addEventListener("pointermove", (event) => (mouse = event.pointerType === "mouse"));
    to.on("mousemove", TRAFFIC_LAYER, (event: MapLayerMouseEvent) => {
      const thing = thingOf(event.features?.[0]);
      if (!thing || !mouse) return;
      to.getCanvas().style.cursor = "pointer";
      hover?.rest(
        `${thing.layer}:${thing.id}`,
        () => boxOf(to, thing.layer, thing.id),
        () => content(thing.layer, thing.id),
      );
    });
    to.on("mouseleave", TRAFFIC_LAYER, () => {
      to.getCanvas().style.cursor = "";
      hover?.hide();
    });
  }

  /** A click on the map: on a thing, its card opens (true); anywhere else the card that is open closes (false), and the map goes on with the click. */
  function clicked(event?: { point?: { x: number; y: number } }): boolean {
    const to = map();
    const hit = to && event?.point && to.getLayer(TRAFFIC_LAYER) ? thingOf(to.queryRenderedFeatures(reach(event.point), { layers: [TRAFFIC_LAYER] })[0]) : null;
    if (hit === null) {
      traffic.close();
      return false;
    }
    hover?.hide();
    traffic.open(hit.layer, hit.id);
    return true;
  }

  return {
    add: (to: MapLibreMap): void => addTrafficLayers(to, trafficFeatures(traffic.tables.value.values(), page.now.value), trail()),
    listen,
    clicked,
    counts: computed(() => trafficCounts(traffic.tables.value, page.now.value)),
    credits: computed<ServiceName[]>(() =>
      traffic.looked.value.flatMap((layer) => {
        const source = page.map.value?.layers.find((one) => one.layer === layer)?.source ?? "none";
        return isService(source) ? [source] : [];
      }),
    ),
    shapes: computed(() => traffic.looked.value.includes("aircraft")),
  };
}
