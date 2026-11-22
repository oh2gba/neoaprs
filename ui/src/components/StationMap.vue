<script setup lang="ts">
// The map: the daemon's base map (no request leaves the machine), a marker with the APRS symbol and
// call for every station with a position, and a track line for stations with more than one position
// (the selected station's is heavier, with a dot at each position: lib/tracklayers.ts). A resting
// mouse shows a card of the station's facts (lib/hovercard.ts); the selected station's route to our
// own station is drawn (lib/routeline.ts). Markers dim and tracks fade towards the station's
// timeout; a station heard direct within the hour has a ring; a station past its timeout is not
// drawn unless selected. The daemon always has the shipped world map; with only that, a note says
// there is no detailed map and offers to go where it is made (not while the guide is open or a
// download runs). When the daemon makes the files again (`filesKey` changes) the style is set
// again. One map for the life of the page, opened where we are (zoom 9; on the world with no
// position) or where it was left; the colour scheme follows the system. While the guide asks for a
// position (`picking`) a click is a place (`pick`) and the guide's place (`pin`) has a marker the
// map flies to when typed. Our own object or item (`own`) has a draggable marker; the drop is its
// new place (`move`). A right-click or long press opens the map menu (useMapMenu, MapMenu): copy
// the place, Statistics, Packets, Monitor (cards over the map), and layer toggles (MapLayers). A
// station with a range (PHG or RNG) has a pale circle under the markers (lib/rangecircles.ts), and
// picking it fits the map to the circle (useMapFollow). While the beacon is mobile and the GPS has
// a fix, Follow me keeps the map centred on the fix.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { GeoJSONSource, Map as MapLibreMap, Marker } from "maplibre-gl";
import { locale, t } from "@/i18n";
import MapAttribution from "@/components/MapAttribution.vue";
import MapLayers from "@/components/MapLayers.vue";
import { archiveUrl, archivesPresent, glyphsUrl, loadMapEngine } from "@/lib/basemap";
import { BASEMAP_FILE, WORLD_FILE, basemapStyle, MAX_ZOOM, OPEN_ZOOM, type Archives } from "@/lib/basemapstyle";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { useMapBoxLayers } from "@/composables/useMapBoxLayers";
import { useMapControlLabels } from "@/composables/useMapControlLabels";
import { useClearOfCard } from "@/composables/useClearOfCard";
import { useFollowMe } from "@/composables/useFollowMe";
import { useMapFollow } from "@/composables/useMapFollow";
import { useMapNote } from "@/composables/useMapNote";
import { useResized } from "@/composables/useResized";
import { buildMarkerDom, paintMarker } from "@/lib/markerdom";
import { readView, writeView, type Focus, type Home, type Placed } from "@/lib/mapview";
import { markerStep, timedOut } from "@/lib/aging";
import { HoverCard } from "@/lib/hovercard";
import { filesKey } from "@/lib/mapfetch";
import { rangeCircleOf } from "@/lib/nearby";
import { heardDirectRecently } from "@/lib/routes";
import { routeFeatures } from "@/lib/routeline";
import { addRouteLayers, ROUTE_SOURCE } from "@/lib/routelayers";
import { addTrackLayers, setTrackData } from "@/lib/tracklayers";
import { placePin } from "@/lib/pinmarker";
import MapMenu from "@/components/MapMenu.vue";
import { useMapMenu, type MapCard } from "@/composables/useMapMenu";
import ReplayBar from "@/components/ReplayBar.vue";
import { useMapReplay } from "@/composables/useMapReplay";
import { hasPosition } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";

// where the map opens while we have no position
const WORLD_VIEW = { lat: 20, lon: 0, zoom: 1.5 };
const LABELS_FROM_ZOOM = 8;

const props = withDefaults(
  defineProps<{
    selected: string | null;
    /**
     * The stations of the other open cards (Ctrl+click): their markers are marked like the selected
     * one's (the route is drawn only for the selected one).
     */
    others?: readonly string[];
    focus: Focus | null;
    /** A click on the map is a place for the first-run guide. */
    picking?: boolean;
    /** The place the first-run guide holds, shown with a marker. */
    pin?: Home | null;
    /** The replay is open (Esc closes it with the cards). */
    replay?: boolean;
  }>(),
  { others: () => [], picking: false, pin: null, replay: false },
);
const emit = defineEmits<{
  select: [call: string | null, multi?: boolean];
  download: [];
  pick: [at: Home];
  move: [call: string, lat: number, lon: number];
  card: [name: MapCard];
  replay: [open: boolean];
}>();
const [page, radios] = [useDaemonContext(), useRadios()];
/**
 * Changes when the map files on the daemon change (their dates); null until the daemon has told.
 */
const mapFiles = computed(() => filesKey(page.map.value));
const [root, host] = [ref<HTMLElement | null>(null), ref<HTMLElement | null>(null)];
const card = useClearOfCard(root, host);
const stationOf = (call: string): StationRow | undefined => page.stations.value.get(call);
const selectedCall = (): string | null => props.selected;
const box = useMapBoxLayers(() => map, selectedCall);
const labelControls = useMapControlLabels(host);
useResized(host, () => map?.resize());
const { following, canFollow, followAt, release } = useFollowMe(page.gps);
const { files, engineFailed, unreadable, note, offerDownload, onMapError } = useMapNote(page);
const placed = new Map<string, Placed>();
let map: MapLibreMap | null = null;
let engine: Awaited<ReturnType<typeof loadMapEngine>> | null = null;
// counts the times the files were made again: the addresses carry it so the archive reader starts
// afresh
let generation = 0;
let seenKey: string | null = mapFiles.value;
let shown = "";
let centred = true;
let gone = false;
let pinMarker: Marker | null = null;
let hover: HoverCard | null = null;
// the pin moved because the map was clicked: the map is where the user is looking already
let clicked = false;
let picks = 0;
// the marker clicked last: the map fits a digipeater's range circle when it is one
const markerPick = ref<Focus | null>(null);

/**
 * The tracks are drawn again once a minute and when a station changes; the fading goes in steps
 * that wide.
 */
const minute = computed(() => Math.floor(page.now.value / 60_000));

const archives = (): Archives => ({
  detail: files.value.detail ? archiveUrl(BASEMAP_FILE, generation > 0 ? String(generation) : "") : null,
  world: files.value.world ? archiveUrl(WORLD_FILE, generation > 0 ? String(generation) : "") : null,
});
const styleFor = (dark: boolean) => basemapStyle(archives(), dark, glyphsUrl());

/** The daemon has other files: ask which, and set the style again if the addresses changed. */
async function refreshBasemap(): Promise<void> {
  files.value = await archivesPresent();
  if (gone || !map) return;
  const now = JSON.stringify(archives());
  if (now === shown) return;
  shown = now;
  unreadable.value = [];
  map.setStyle(styleFor(page.dark.value));
}

function drawRoute(): void {
  const row = props.selected === null ? undefined : page.stations.value.get(props.selected);
  void map?.getSource<GeoJSONSource>(ROUTE_SOURCE)?.setData(routeFeatures(row, page.stations.value, page.home.value));
}

function addLayers(): void {
  if (!map) return;
  box.add(map);
  addTrackLayers(map);
  drawTracks();
  addRouteLayers(map, routeFeatures(undefined, page.stations.value, null));
  drawRoute();
  replay.add();
}

/**
 * The stations drawn: with a position and not past their timeout (a station with an open card is
 * drawn with its track regardless).
 */
const drawn = (): StationRow[] =>
  [...page.stations.value.values()].filter(
    (row) => hasPosition(row) && (isOpen(row.call) || !timedOut(page.aging.value, row, page.now.value)),
  );

function drawTracks(): void {
  if (map) setTrackData(map, drawn(), openCalls(), page.now.value, page.aging.value, box.tracks());
}

function makePlaced(call: string): Placed | null {
  if (!map || !engine) return null;
  const dom = buildMarkerDom();
  dom.root.addEventListener("click", (event: MouseEvent) => {
    event.stopPropagation();
    hover?.hide();
    emit("select", call, event.ctrlKey || event.metaKey);
    markerPick.value = { call, n: ++picks };
  });
  hover?.attach(dom.root, call);
  const marker = new engine.Marker({ element: dom.root, anchor: "center" }).setLngLat([0, 0]).addTo(map);
  marker.on("dragend", () => {
    const at = marker.getLngLat();
    emit("move", call, at.lat, at.lng);
  });
  return { marker, dom, lat: NaN, lon: NaN };
}

/**
 * A station with an open card (the selected one or another): its marker shows and is marked even
 * past its timeout.
 */
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

/**
 * The marker of the guide's place: made when there is one, moved when it changes, removed when it
 * is gone.
 */
function syncPin(): void {
  if (map && engine) pinMarker = placePin(engine, map, pinMarker, props.pin, pickAt);
}

function onClick(event?: {
  lngLat?: { lat: number; lng: number };
  point?: { x: number; y: number };
  originalEvent?: MouseEvent;
}): void {
  if (!props.picking && box.clicked(event)) return;
  if (!(event?.originalEvent?.ctrlKey || event?.originalEvent?.metaKey)) emit("select", null);
  if (props.picking && event?.lngLat) pickAt(event.lngLat.lat, event.lngLat.lng);
}

function pickAt(lat: number, lon: number): void {
  clicked = true;
  emit("pick", { lat, lon });
  void nextTick(() => (clicked = false));
}

const mapMenu = useMapMenu(host, () => ({ map, hover }));
const menuEvents = {
  close: () => mapMenu.close(),
  card: (name: MapCard) => emit("card", name),
  replay: () => emit("replay", true),
};
const replay = useMapReplay(() => ({ map, engine, open: props.replay }));

function showLabels(): void {
  host.value?.classList.toggle("labels-off", (map?.getZoom() ?? OPEN_ZOOM) < LABELS_FROM_ZOOM);
}

async function create(): Promise<void> {
  files.value = await archivesPresent();
  engine = await loadMapEngine().catch(() => null);
  if (!engine) {
    engineFailed.value = true;
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
      attributionControl: false, // the page draws its own (i)
    });
  } catch {
    engineFailed.value = true; // no WebGL
    return;
  }
  map.touchZoomRotate.disableRotation();
  map.addControl(new engine.NavigationControl({ showCompass: false }), "top-left");
  labelControls();
  map.on("style.load", addLayers);
  box.listen(map, hover);
  map.on("movestart", () => hover?.hide());
  map.on("dragstart", release);
  map.on("click", onClick);
  map.on("contextmenu", mapMenu.onContextMenu);
  map.on("error", onMapError);
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

watch(
  [() => [...page.stations.value.values()], () => [props.selected, props.others, page.aging.value.defaultMin]],
  () => {
    syncMarkers();
    drawTracks();
    drawRoute();
  },
);
watch(() => page.now.value, syncMarkers);
watch([minute, box.tracks], drawTracks);
useMapFollow(() => map, card, {
  focus: () => props.focus,
  selected: () => props.selected,
  station: stationOf,
  marker: (call) => placed.get(call),
  follow: followAt,
  pick: () => markerPick.value,
  circle: (call) => rangeCircleOf(page.stations.value.values(), call),
});
watch(page.home, (home) => {
  drawRoute();
  if (!map || !home || centred) return;
  centred = true;
  map.jumpTo({ center: [home.lon, home.lat], zoom: OPEN_ZOOM });
});
watch(
  () => [props.pin?.lat, props.pin?.lon],
  () => {
    syncPin();
    const at = props.pin;
    if (map && at && !clicked) map.flyTo({ center: [at.lon, at.lat], zoom: Math.max(map.getZoom(), OPEN_ZOOM) });
  },
);
watch(mapFiles, (key) => {
  if (key === null || key === seenKey) return;
  if (seenKey !== null) generation += 1;
  seenKey = key;
  void refreshBasemap();
});
watch([page.dark, locale], ([dark]) => map?.setStyle(styleFor(dark)));

onMounted(() => {
  if (root.value) hover = new HoverCard(root.value, stationOf, () => page.now.value, radios);
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
  <!-- The page's classes go on the root, never on the map's box: MapLibre sets that -->
  <!-- box's classes (`maplibregl-map`), and a class bound by Vue there replaces them all. -->
  <div
    ref="root"
    class="stationmap"
    :class="{ 'map-picking': props.picking, replaying: props.replay }"
    v-on="mapMenu.on"
  >
    <div ref="host" class="mapbox" role="application" :aria-label="t('map.label')"></div>
    <MapMenu
      v-if="mapMenu.menu.value"
      :key="mapMenu.key.value"
      v-bind="mapMenu.menu.value"
      :trigger="host"
      v-on="menuEvents"
    />
    <ReplayBar v-if="props.replay" :replay="replay.clock" @close="emit('replay', false)" />
    <button
      v-if="canFollow"
      class="btn followme"
      :class="{ primary: following }"
      type="button"
      :aria-pressed="following"
      @click="following = !following"
    >
      {{ t("map.follow_me") }}
    </button>
    <MapLayers :place="box.place.value" :counts="box.counts.value" />
    <MapAttribution :credits="box.credits.value" :aircraft="box.shapes.value" />
  </div>
  <div v-if="note" class="mapnote" role="status">
    <div class="mapnote-box">
      <span>{{ t(note) }}</span>
      <button v-if="offerDownload" class="btn" type="button" @click="emit('download')">{{ t("map.download") }}</button>
    </div>
  </div>
</template>
