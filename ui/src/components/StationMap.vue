<script setup lang="ts">
// The map: the base map the daemon serves (no request leaves the machine), a marker with the APRS symbol and the call for every station that has a position, and a line for the track of
// every station that has more than one; a mouse resting on a marker shows a small card with the station's main facts (lib/hovercard.ts), and the selected station has the route its packets come by drawn
// to our own station (lib/routeline.ts). A marker dims and a track fades on the way to the station's timeout, and a station heard direct within the hour has a ring round its marker; a station past it is not drawn (unless it is the selected one, whose marker shows). Without the base map files the background is blank and a line says so, with a button that takes the user to where the map is made, and the stations are drawn all the same;
// when the daemon makes the files again (`filesKey` changes) the style is set again. One map for the life of the page,
// opened where we are (zoom 9; on the world while we have no position) or where it was left; the colour scheme follows the system. While the first-run guide asks for the position (`picking`) a click on the map is a place (`pick`), and the place the guide
// holds (`pin`) has a marker, which the map flies to when it was typed and not clicked. An object or an item of ours (`own`) has a marker that can be dragged: where it is dropped is its new place (`move`).
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { GeoJSONSource, Map as MapLibreMap, Marker } from "maplibre-gl";
import MapAttribution from "@/components/MapAttribution.vue";
import { archiveUrl, archivesPresent, glyphsUrl, loadMapEngine } from "@/lib/basemap";
import {
  BASEMAP_FILE,
  WORLD_FILE,
  basemapStyle,
  MAX_ZOOM,
  NO_BASEMAP_TEXT,
  NO_DETAIL_TEXT,
  NO_ENGINE_TEXT,
  OPEN_ZOOM,
  type Archives,
} from "@/lib/basemapstyle";
import { useClearOfCard } from "@/composables/useClearOfCard";
import { buildMarkerDom, paintMarker, type MarkerDom } from "@/lib/markerdom";
import { readView, writeView, type Focus, type Home } from "@/lib/mapview";
import { markerStep, timedOut, type Aging } from "@/lib/aging";
import { HoverCard } from "@/lib/hovercard";
import { heardDirectRecently } from "@/lib/routes";
import { routeFeatures } from "@/lib/routeline";
import { addRouteLayers, ROUTE_SOURCE } from "@/lib/routelayers";
import { addTrackLayers } from "@/lib/tracklayers";
import { placePin } from "@/lib/pinmarker";
import { hasPosition } from "@/lib/stations";
import { trackLines } from "@/lib/tracks";
import type { StationRow } from "@/protocol/protocol";

const FLY_ZOOM = 11;
const WORLD_VIEW = { lat: 20, lon: 0, zoom: 1.5 }; // where the map opens while we have no position
const LABELS_FROM_ZOOM = 8;

const props = withDefaults(
  defineProps<{
    stations: ReadonlyMap<string, StationRow>;
    selected: string | null;
    focus: Focus | null;
    home: Home | null;
    now: number;
    dark: boolean;
    aging: Aging;
    /** Changes when the map files on the daemon are other ones (their dates); null until the daemon has told. */
    filesKey?: string | null;
    /** A click on the map is a place for the first-run guide. */
    picking?: boolean;
    /** The place the first-run guide holds, shown with a marker. */
    pin?: Home | null;
  }>(),
  { filesKey: null, picking: false, pin: null },
);
const emit = defineEmits<{ select: [call: string | null]; download: []; pick: [at: Home]; move: [call: string, lat: number, lon: number] }>();

interface Placed {
  marker: Marker;
  dom: MarkerDom;
  lat: number;
  lon: number;
}

const root = ref<HTMLElement | null>(null);
const host = ref<HTMLElement | null>(null);
const card = useClearOfCard(root, host);
const note = ref(""); // what stands over the map when there is no base map (or no map engine)
const offerDownload = ref(false); // ... and whether it has the button that goes to where the map is made
const placed = new Map<string, Placed>();
let map: MapLibreMap | null = null;
let engine: Awaited<ReturnType<typeof loadMapEngine>> | null = null;
let hasFiles = { detail: false, world: false }; // which of the two files the daemon has
let generation = 0; // counts the times the files were made again: the addresses carry it, so that the reader of the archives starts afresh
let seenKey: string | null = props.filesKey;
let shown = ""; // the addresses the style on the map was made with
let centred = true; // the view is the one of the last visit, or has been set to where we are
let gone = false;
let pinMarker: Marker | null = null;
let hover: HoverCard | null = null;
let clicked = false; // the pin moved because the map was clicked: the map is where the user is looking already

/** The tracks are drawn again once a minute, and when a station changes; the fading is in steps that wide anyway. */
const minute = computed(() => Math.floor(props.now / 60_000));

const archives = (): Archives => ({
  detail: hasFiles.detail ? archiveUrl(BASEMAP_FILE, generation > 0 ? String(generation) : "") : null,
  world: hasFiles.world ? archiveUrl(WORLD_FILE, generation > 0 ? String(generation) : "") : null,
});
const styleFor = (dark: boolean) => basemapStyle(archives(), dark, glyphsUrl());

function noteBasemap(): void {
  note.value = hasFiles.detail ? "" : hasFiles.world ? NO_DETAIL_TEXT : NO_BASEMAP_TEXT;
  offerDownload.value = !hasFiles.detail;
}

/** The daemon has other files: ask which it has, and set the style again if the addresses are other ones. */
async function refreshBasemap(): Promise<void> {
  hasFiles = await archivesPresent();
  if (gone || !map) return;
  noteBasemap();
  const now = JSON.stringify(archives());
  if (now === shown) return;
  shown = now;
  map.setStyle(styleFor(props.dark));
}

function drawRoute(): void {
  const row = props.selected === null ? undefined : props.stations.get(props.selected);
  void map?.getSource<GeoJSONSource>(ROUTE_SOURCE)?.setData(routeFeatures(row, props.stations, props.home));
}

function addLayers(): void {
  if (!map) return;
  addTrackLayers(map, trackLines([], null, props.now, props.aging));
  drawTracks();
  addRouteLayers(map, routeFeatures(undefined, props.stations, null));
  drawRoute();
}

/** The stations that are drawn: with a position and not past their timeout. */
function drawn(): StationRow[] {
  return [...props.stations.values()].filter((row) => hasPosition(row) && !timedOut(props.aging, row, props.now));
}

function drawTracks(): void {
  void map?.getSource<GeoJSONSource>("tracks")?.setData(trackLines(drawn(), props.selected, props.now, props.aging));
}

function makePlaced(call: string): Placed | null {
  if (!map || !engine) return null;
  const dom = buildMarkerDom();
  dom.root.addEventListener("click", (event) => {
    event.stopPropagation(); // not a click on the map, which lets go of the selection
    hover?.hide();
    emit("select", call);
  });
  hover?.attach(dom.root, call);
  const marker = new engine.Marker({ element: dom.root, anchor: "center" }).setLngLat([0, 0]).addTo(map);
  marker.on("dragend", () => {
    const at = marker.getLngLat();
    emit("move", call, at.lat, at.lng);
  });
  return { marker, dom, lat: NaN, lon: NaN };
}

function syncMarkers(): void {
  if (!map) return;
  const present = new Set<string>();
  for (const row of props.stations.values()) {
    if (!hasPosition(row) || (row.call !== props.selected && timedOut(props.aging, row, props.now))) continue;
    present.add(row.call);
    const one = placed.get(row.call) ?? makePlaced(row.call);
    if (!one) continue;
    placed.set(row.call, one);
    if (one.lat !== row.lat || one.lon !== row.lon) {
      one.marker.setLngLat([row.lon, row.lat]);
      one.lat = row.lat;
      one.lon = row.lon;
    }
    one.marker.setDraggable(row.own);
    paintMarker(one.dom, row, {
      fade: markerStep(props.aging, row, props.now),
      selected: row.call === props.selected,
      direct: heardDirectRecently(row, props.now),
    });
  }
  for (const [call, one] of placed) {
    if (present.has(call)) continue;
    one.marker.remove();
    placed.delete(call);
    hover?.release(call);
  }
  hover?.refresh();
}

/** The marker of the place the guide holds: made when there is one, moved when it changes, gone when it is. */
function syncPin(): void {
  if (map && engine) pinMarker = placePin(engine, map, pinMarker, props.pin, pickAt); // (the pin dropped somewhere else is the place, as a click there would be)
}

function onClick(event?: { lngLat?: { lat: number; lng: number } }): void {
  emit("select", null);
  if (props.picking && event?.lngLat) pickAt(event.lngLat.lat, event.lngLat.lng);
}

function pickAt(lat: number, lon: number): void {
  clicked = true;
  emit("pick", { lat, lon });
  void nextTick(() => (clicked = false)); // after the update the click causes
}

function showLabels(): void {
  host.value?.classList.toggle("labels-off", (map?.getZoom() ?? OPEN_ZOOM) < LABELS_FROM_ZOOM);
}

async function create(): Promise<void> {
  hasFiles = await archivesPresent();
  noteBasemap();
  engine = await loadMapEngine().catch(() => null);
  if (!engine) {
    note.value = NO_ENGINE_TEXT;
    offerDownload.value = false;
    return;
  }
  if (gone || !host.value) return;
  shown = JSON.stringify(archives());
  const view = readView();
  centred = view !== null;
  const home = view ?? (props.home ? { ...props.home, zoom: OPEN_ZOOM } : WORLD_VIEW);
  centred ||= props.home !== null;
  try {
    map = new engine.Map({
      container: host.value,
      style: styleFor(props.dark),
      center: [home.lon, home.lat],
      zoom: home.zoom,
      maxZoom: MAX_ZOOM,
      dragRotate: false,
      pitchWithRotate: false,
      attributionControl: false, // the page draws its own: a small (i), closed until clicked
    });
  } catch {
    note.value = NO_ENGINE_TEXT; // a browser without WebGL
    offerDownload.value = false;
    return;
  }
  map.touchZoomRotate.disableRotation();
  map.addControl(new engine.NavigationControl({ showCompass: false }), "top-left");
  map.on("style.load", addLayers);
  map.on("movestart", () => hover?.hide());
  map.on("click", onClick);
  map.on("zoom", showLabels);
  map.on("moveend", () => {
    if (!map) return;
    const at = map.getCenter();
    writeView({ lat: at.lat, lon: at.lng, zoom: map.getZoom() });
  });
  showLabels();
  syncMarkers();
  syncPin();
}

watch([() => [...props.stations.values()], () => [props.selected, [...props.aging.timeouts], props.aging.defaultMin]], () => {
  syncMarkers();
  drawTracks();
  drawRoute();
});
watch(() => props.now, syncMarkers);
watch(minute, drawTracks);
// (after the page is drawn, so that the card of the station is there to keep clear of)
watch(
  () => props.focus,
  (focus) => {
    const row = focus ? props.stations.get(focus.call) : undefined;
    if (map && row && hasPosition(row)) map.flyTo({ center: [row.lon, row.lat], zoom: Math.max(map.getZoom(), FLY_ZOOM), ...card.flightOffset() });
  },
  { flush: "post" },
);
watch(
  () => props.selected,
  (call) => {
    const one = call === null ? undefined : placed.get(call);
    if (map && one) card.panClear(map, one);
  },
  { flush: "post" },
);
watch(
  () => props.home,
  (home) => {
    drawRoute();
    if (!map || !home || centred) return;
    centred = true;
    map.jumpTo({ center: [home.lon, home.lat], zoom: OPEN_ZOOM });
  },
);
watch(
  () => [props.pin?.lat, props.pin?.lon],
  () => {
    syncPin();
    const at = props.pin;
    if (map && at && !clicked) map.flyTo({ center: [at.lon, at.lat], zoom: Math.max(map.getZoom(), OPEN_ZOOM) });
  },
);
watch(
  () => props.filesKey,
  (key) => {
    if (key === null || key === seenKey) return;
    if (seenKey !== null) generation += 1; // (the first word from the daemon is not a change)
    seenKey = key;
    void refreshBasemap();
  },
);
watch(
  () => props.dark,
  (dark) => map?.setStyle(styleFor(dark)),
);

onMounted(() => {
  if (root.value)
    hover = new HoverCard(
      root.value,
      (call) => props.stations.get(call),
      () => props.now,
    );
  void create();
});
onBeforeUnmount(() => {
  gone = true;
  hover?.destroy();
  hover = null;
  for (const one of placed.values()) one.marker.remove();
  placed.clear();
  pinMarker?.remove();
  pinMarker = null;
  map?.remove();
  map = null;
});
</script>

<template>
  <div ref="root" class="stationmap">
    <div ref="host" class="mapbox" :class="{ 'map-picking': props.picking }" role="application" aria-label="Map of the stations"></div>
    <div v-if="note" class="mapnote" role="status">
      <div class="mapnote-box">
        <span>{{ note }}</span>
        <button v-if="offerDownload" class="btn small" type="button" @click="emit('download')">Download</button>
      </div>
    </div>
    <MapAttribution />
  </div>
</template>
