<script setup lang="ts">
// The map: the base map the daemon serves (no request leaves the machine), a marker with the APRS symbol and the call for every station that has a position, and a line for the track of
// every station that has more than one; a mouse resting on a marker shows a small card with the station's main facts (lib/hovercard.ts), and the selected station has the route its packets come by drawn
// to our own station (lib/routeline.ts). A marker dims and a track fades on the way to the station's timeout, and a station heard direct within the hour has a ring round its marker; a station past it is not drawn (unless it is the selected one, whose marker shows). Without the base map files the background is blank and a line says so, with a button that takes the user to where the map is made, and the stations are drawn all the same;
// when the daemon makes the files again (`filesKey` changes) the style is set again. One map for the life of the page,
// opened where we are (zoom 9; on the world while we have no position) or where it was left; the colour scheme follows the system. While the first-run guide asks for the position (`picking`) a click on the map is a place (`pick`), and the place the guide
// holds (`pin`) has a marker, which the map flies to when it was typed and not clicked. An object or an item of ours (`own`) has a marker that can be dragged: where it is dropped is its new place (`move`).
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { GeoJSONSource, Map as MapLibreMap, Marker } from "maplibre-gl";
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import MapAttribution from "@/components/MapAttribution.vue";
import { archiveUrl, archivesPresent, glyphsUrl, loadMapEngine } from "@/lib/basemap";
import { BASEMAP_FILE, WORLD_FILE, basemapStyle, MAX_ZOOM, OPEN_ZOOM, type Archives } from "@/lib/basemapstyle";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useClearOfCard } from "@/composables/useClearOfCard";
import { useMapFollow } from "@/composables/useMapFollow";
import { useResized } from "@/composables/useResized";
import { buildMarkerDom, paintMarker, type MarkerDom } from "@/lib/markerdom";
import { readView, writeView, type Focus, type Home } from "@/lib/mapview";
import { markerStep, timedOut } from "@/lib/aging";
import { HoverCard } from "@/lib/hovercard";
import { filesKey } from "@/lib/mapfetch";
import { heardDirectRecently } from "@/lib/routes";
import { routeFeatures } from "@/lib/routeline";
import { addRouteLayers, ROUTE_SOURCE } from "@/lib/routelayers";
import { addTrackLayers } from "@/lib/tracklayers";
import { placePin } from "@/lib/pinmarker";
import { hasPosition } from "@/lib/stations";
import { trackLines } from "@/lib/tracks";
import type { StationRow } from "@/protocol/protocol";

const WORLD_VIEW = { lat: 20, lon: 0, zoom: 1.5 }; // where the map opens while we have no position
const LABELS_FROM_ZOOM = 8;

const props = withDefaults(
  defineProps<{
    selected: string | null;
    /** The stations of the other cards that are open (Ctrl+click): their markers are marked as the selected one's is (the route is drawn for the selected one only). */
    others?: readonly string[];
    focus: Focus | null;
    /** A click on the map is a place for the first-run guide. */
    picking?: boolean;
    /** The place the first-run guide holds, shown with a marker. */
    pin?: Home | null;
  }>(),
  { others: () => [], picking: false, pin: null },
);
const emit = defineEmits<{ select: [call: string | null, multi?: boolean]; download: []; pick: [at: Home]; move: [call: string, lat: number, lon: number] }>();
const page = useDaemonContext();
/** Changes when the map files on the daemon are other ones (their dates); null until the daemon has told. */
const mapFiles = computed(() => filesKey(page.map.value));

interface Placed {
  marker: Marker;
  dom: MarkerDom;
  lat: number;
  lon: number;
}

const root = ref<HTMLElement | null>(null);
const host = ref<HTMLElement | null>(null);
const card = useClearOfCard(root, host);
useResized(host, () => map?.resize());
const note = ref<MessageId | "">(""); // what stands over the map when there is no base map (or no map engine): the id of its message
const offerDownload = ref(false); // ... and whether it has the button that goes to where the map is made
const placed = new Map<string, Placed>();
let map: MapLibreMap | null = null;
let engine: Awaited<ReturnType<typeof loadMapEngine>> | null = null;
let hasFiles = { detail: false, world: false }; // which of the two files the daemon has
let generation = 0; // counts the times the files were made again: the addresses carry it, so that the reader of the archives starts afresh
let seenKey: string | null = mapFiles.value;
let shown = ""; // the addresses the style on the map was made with
let centred = true; // the view is the one of the last visit, or has been set to where we are
let gone = false;
let pinMarker: Marker | null = null;
let hover: HoverCard | null = null;
let clicked = false; // the pin moved because the map was clicked: the map is where the user is looking already

/** The tracks are drawn again once a minute, and when a station changes; the fading is in steps that wide anyway. */
const minute = computed(() => Math.floor(page.now.value / 60_000));

const archives = (): Archives => ({
  detail: hasFiles.detail ? archiveUrl(BASEMAP_FILE, generation > 0 ? String(generation) : "") : null,
  world: hasFiles.world ? archiveUrl(WORLD_FILE, generation > 0 ? String(generation) : "") : null,
});
const styleFor = (dark: boolean) => basemapStyle(archives(), dark, glyphsUrl());

function noteBasemap(): void {
  note.value = hasFiles.detail ? "" : hasFiles.world ? "map.note.no_detail" : "map.note.no_basemap";
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
  map.setStyle(styleFor(page.dark.value));
}

function drawRoute(): void {
  const row = props.selected === null ? undefined : page.stations.value.get(props.selected);
  void map?.getSource<GeoJSONSource>(ROUTE_SOURCE)?.setData(routeFeatures(row, page.stations.value, page.home.value));
}

function addLayers(): void {
  if (!map) return;
  addTrackLayers(map, trackLines([], null, page.now.value, page.aging.value));
  drawTracks();
  addRouteLayers(map, routeFeatures(undefined, page.stations.value, null));
  drawRoute();
}

/** The stations that are drawn: with a position and not past their timeout (a station whose card is open is drawn, with its track, whatever its timeout). */
function drawn(): StationRow[] {
  return [...page.stations.value.values()].filter((row) => hasPosition(row) && (isOpen(row.call) || !timedOut(page.aging.value, row, page.now.value)));
}

function drawTracks(): void {
  void map?.getSource<GeoJSONSource>("tracks")?.setData(trackLines(drawn(), openCalls(), page.now.value, page.aging.value));
}

function makePlaced(call: string): Placed | null {
  if (!map || !engine) return null;
  const dom = buildMarkerDom();
  dom.root.addEventListener("click", (event: MouseEvent) => {
    event.stopPropagation(); // not a click on the map, which lets go of the selection
    hover?.hide();
    emit("select", call, event.ctrlKey || event.metaKey); // (Ctrl, or Cmd on a Mac, adds the card to the open ones)
  });
  hover?.attach(dom.root, call);
  const marker = new engine.Marker({ element: dom.root, anchor: "center" }).setLngLat([0, 0]).addTo(map);
  marker.on("dragend", () => {
    const at = marker.getLngLat();
    emit("move", call, at.lat, at.lng);
  });
  return { marker, dom, lat: NaN, lon: NaN };
}

/** A station with a card open (the selected one, or one of the others): its marker shows, and is marked, even when it is past its timeout. */
const isOpen = (call: string): boolean => call === props.selected || props.others.includes(call);
const openCalls = (): string[] => (props.selected === null ? [...props.others] : [...props.others, props.selected]);

function syncMarkers(): void {
  if (!map) return;
  const present = new Set<string>();
  for (const row of page.stations.value.values()) {
    if (!hasPosition(row) || (!isOpen(row.call) && timedOut(page.aging.value, row, page.now.value))) continue;
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
      fade: markerStep(page.aging.value, row, page.now.value),
      selected: isOpen(row.call),
      direct: heardDirectRecently(row, page.now.value),
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

function onClick(event?: { lngLat?: { lat: number; lng: number }; originalEvent?: MouseEvent }): void {
  if (!(event?.originalEvent?.ctrlKey || event?.originalEvent?.metaKey)) emit("select", null); // (a Ctrl+click beside a marker leaves the cards open)
  if (props.picking && event?.lngLat) pickAt(event.lngLat.lat, event.lngLat.lng);
}

function pickAt(lat: number, lon: number): void {
  clicked = true;
  emit("pick", { lat, lon });
  void nextTick(() => (clicked = false)); // after the update the click causes
}

/** The words of the map engine's own controls in the page's language (it has English only): the zoom buttons and the label of its canvas. Said again when the language changes. */
function labelControls(): void {
  const label = (selector: string, text: string): void => {
    const el = host.value?.querySelector(selector);
    el?.setAttribute("aria-label", text);
    if (el?.hasAttribute("title")) el.setAttribute("title", text);
  };
  label(".maplibregl-ctrl-zoom-in", t("map.zoom_in"));
  label(".maplibregl-ctrl-zoom-out", t("map.zoom_out"));
  label(".maplibregl-canvas", t("map.label"));
}
watch(() => [t("map.zoom_in"), t("map.zoom_out"), t("map.label")], labelControls);

function showLabels(): void {
  host.value?.classList.toggle("labels-off", (map?.getZoom() ?? OPEN_ZOOM) < LABELS_FROM_ZOOM);
}

async function create(): Promise<void> {
  hasFiles = await archivesPresent();
  noteBasemap();
  engine = await loadMapEngine().catch(() => null);
  if (!engine) {
    note.value = "map.note.no_engine";
    offerDownload.value = false;
    return;
  }
  if (gone || !host.value) return;
  shown = JSON.stringify(archives());
  const view = readView();
  centred = view !== null;
  const home = view ?? (page.home.value ? { ...page.home.value, zoom: OPEN_ZOOM } : WORLD_VIEW);
  centred ||= page.home.value !== null;
  try {
    map = new engine.Map({
      container: host.value,
      style: styleFor(page.dark.value),
      center: [home.lon, home.lat],
      zoom: home.zoom,
      maxZoom: MAX_ZOOM,
      dragRotate: false,
      pitchWithRotate: false,
      attributionControl: false, // the page draws its own: a small (i), closed until clicked
    });
  } catch {
    note.value = "map.note.no_engine"; // a browser without WebGL
    offerDownload.value = false;
    return;
  }
  map.touchZoomRotate.disableRotation();
  map.addControl(new engine.NavigationControl({ showCompass: false }), "top-left");
  labelControls();
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

watch([() => [...page.stations.value.values()], () => [props.selected, props.others, [...page.aging.value.timeouts], page.aging.value.defaultMin]], () => {
  syncMarkers();
  drawTracks();
  drawRoute();
});
watch(() => page.now.value, syncMarkers);
watch(minute, drawTracks);
useMapFollow(() => map, card, {
  focus: () => props.focus,
  selected: () => props.selected,
  station: (call) => page.stations.value.get(call),
  marker: (call) => placed.get(call),
});
watch(
  () => page.home.value,
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
  () => mapFiles.value,
  (key) => {
    if (key === null || key === seenKey) return;
    if (seenKey !== null) generation += 1; // (the first word from the daemon is not a change)
    seenKey = key;
    void refreshBasemap();
  },
);
watch(
  () => page.dark.value,
  (dark) => map?.setStyle(styleFor(dark)),
);

onMounted(() => {
  if (root.value)
    hover = new HoverCard(
      root.value,
      (call) => page.stations.value.get(call),
      () => page.now.value,
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
    <div ref="host" class="mapbox" :class="{ 'map-picking': props.picking }" role="application" :aria-label="t('map.label')"></div>
    <div v-if="note" class="mapnote" role="status">
      <div class="mapnote-box">
        <span>{{ t(note) }}</span>
        <button v-if="offerDownload" class="btn small" type="button" @click="emit('download')">{{ t("map.download") }}</button>
      </div>
    </div>
    <MapAttribution />
  </div>
</template>
