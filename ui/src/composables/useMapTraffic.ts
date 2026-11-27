// The aircraft and ships layer of the map: redrawn when a table arrives and as the clock moves
// (marks fade by age), and moved at every step of the map's motion (`mover`, gliding each thing
// between its reports). A mouse resting on one shows the hover box, a click opens its card and a
// click elsewhere closes it (`clicked`). Also gives the per-layer `counts`, the `credits` and
// whether aircraft are drawn (`shapes`).
import { computed, watch } from "vue";
import type { MapGeoJSONFeature, MapLayerMouseEvent, Map as MapLibreMap } from "maplibre-gl";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { motionNow, type Mover } from "@/composables/useMapMotion";
import type { Glide } from "@/lib/layers/glide";
import type { HoverCard, HoverContent } from "@/lib/hovercard";
import { hoverRows, thingSub, thingTitle } from "@/lib/layers/card";
import { isService, type LayerName, type ServiceName } from "@/lib/layers/sources";
import { MARKS, MARK_SIZE, edgeWidth, markBox } from "@/lib/layers/marks";
import {
  NO_TRAFFIC,
  glidedFeatures,
  kindShape,
  liveThings,
  nextGlides,
  sideOf,
  thingKey,
  thingShape,
  trafficCounts,
  trafficFeatures,
  type TrafficCollection,
} from "@/lib/layers/traffic";
import { NO_TRAIL, trailKey, trailLines } from "@/lib/layers/trail";
import type { TrackCollection } from "@/lib/tracks";
import type { LayerThingsMessage } from "@/protocol/protocol";
import { TRAFFIC_LAYER, addTrafficLayers, setTrafficData, setTrailData } from "@/lib/layers/trafficlayers";

// Pixels each way round a click or tap; the topmost mark found is the one meant.
const REACH = 6;

const reach = (point: { x: number; y: number }): [[number, number], [number, number]] => [
  [point.x - REACH, point.y - REACH],
  [point.x + REACH, point.y + REACH],
];

function thingOf(feature: MapGeoJSONFeature | undefined): { layer: LayerName; id: string } | null {
  const layer: unknown = feature?.properties.layer;
  const id: unknown = feature?.properties.id;
  return (layer === "aircraft" || layer === "ships") && typeof id === "string" ? { layer, id } : null;
}

function useOpenTrail(map: () => MapLibreMap | null): () => TrackCollection {
  const page = useDaemonContext();
  const traffic = page.traffic;
  const lines = (): TrackCollection => {
    const open = traffic.card.value;
    return open ? trailLines(trailKey(open.layer, open.thing.id), traffic.trail.value, page.now.value) : NO_TRAIL;
  };
  const openKey = computed(() =>
    traffic.card.value ? trailKey(traffic.card.value.layer, traffic.card.value.thing.id) : null,
  );
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
  let hover: HoverCard | null = null;
  const traffic = page.traffic;
  let glides = new Map<string, Glide>();
  let drawn: TrafficCollection = NO_TRAFFIC;
  // When each table came, on the motion's clock.
  const received = new WeakMap<LayerThingsMessage, number>();
  watch(
    traffic.tables,
    (tables) => {
      const now = motionNow();
      for (const table of tables.values()) if (!received.has(table)) received.set(table, now);
      glides = nextGlides(glides, tables.values(), now, (table) => received.get(table) ?? now);
    },
    { flush: "sync", immediate: true },
  );
  const placed = (nowMs: number): TrafficCollection => glidedFeatures(drawn, glides, nowMs);
  const draw = (): void => {
    drawn = trafficFeatures(traffic.tables.value.values(), page.now.value);
    const to = map();
    if (to) setTrafficData(to, placed(motionNow()));
  };
  watch([traffic.tables, page.now], draw);
  const trail = useOpenTrail(map);
  const mover: Mover = {
    active: () => traffic.looked.value.length > 0,
    draw: (nowMs) => {
      const to = map();
      if (to && drawn.features.length > 0) setTrafficData(to, placed(nowMs));
    },
  };

  function content(layer: LayerName, id: string): HoverContent | null {
    const table = traffic.tables.value.get(layer);
    const thing = table ? liveThings(table, page.now.value).find((one) => one.id === id) : undefined;
    if (!thing) return null;
    const mark = MARKS[kindShape(layer, thing)];
    return {
      title: thingTitle(layer, thing),
      sub: thingSub(layer),
      rows: hoverRows(layer, thing, page.now.value),
      mark: { d: mark.d, viewBox: markBox(mark), bad: thing.emergency, edge: mark.edge ? edgeWidth(mark) : undefined },
    };
  }

  function boxOf(to: MapLibreMap, layer: LayerName, id: string): DOMRect {
    const thing = traffic.tables.value.get(layer)?.things.find((one) => one.id === id);
    const frame = to.getContainer().getBoundingClientRect();
    const key = thingKey(layer, id);
    const here = placed(motionNow()).features.find((one) => one.properties.key === key)?.geometry.coordinates;
    const at = here ? to.project(here) : { x: 0, y: 0 };
    const side = thing ? sideOf(thingShape(layer, thing)) : MARK_SIZE;
    return new DOMRect(frame.left + at.x - side / 2, frame.top + at.y - side / 2, side, side);
  }

  function listen(to: MapLibreMap, card: HoverCard | null): void {
    hover = card;
    let mouse = false;
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

  /** A click on the map: true if it opened a thing's card, false if it closed the open one. */
  function clicked(event?: { point?: { x: number; y: number } }): boolean {
    const to = map();
    const hit =
      to && event?.point && to.getLayer(TRAFFIC_LAYER)
        ? thingOf(to.queryRenderedFeatures(reach(event.point), { layers: [TRAFFIC_LAYER] })[0])
        : null;
    if (hit === null) {
      traffic.close();
      return false;
    }
    hover?.hide();
    traffic.open(hit.layer, hit.id);
    return true;
  }

  return {
    add: (to: MapLibreMap): void => {
      drawn = trafficFeatures(traffic.tables.value.values(), page.now.value);
      addTrafficLayers(to, placed(motionNow()), trail());
    },
    mover,
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
