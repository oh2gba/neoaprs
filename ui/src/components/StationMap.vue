<script setup lang="ts">
// The ships and the aircraft of the open feeds (ais/enabled, adsb/enabled) are layers of their own under the markers, each turned the way it heads, with a card for the one clicked (composables/useTrafficMap.ts); only received, never sent.
// The map: the base map the daemon serves (no request leaves the machine), a marker with the APRS symbol and the call for every station that has a position, and a line for the track of
// every station that has more than one (the selected station's heavier, solid, on a pale casing and with a dot at each position: lib/tracklayers.ts); a mouse resting on a marker shows a small card with the station's main facts (lib/hovercard.ts), and the selected station has the route its packets come by drawn
// to our own station (lib/routeline.ts). A marker dims and a track fades on the way to the station's timeout, and a station heard direct within the hour has a ring round its marker; a station past it is not drawn (unless it is the selected one, whose marker shows). The daemon always has a world map (the one that ships with the program), so the map is drawn from the first second; without any base map file, or when the files cannot be read, the background is blank and a line says so (over the first-run guide too: it is
// the note's own layer, above the guide), and the stations are drawn all the same. With only the world map a line says there is no detailed map, with a button that takes the user to where it is made (not while the first-run guide is open, which makes it itself, or a download runs);
// when the daemon makes the files again (`filesKey` changes) the style is set again. One map for the life of the page,
// opened where we are (zoom 9; on the world while we have no position) or where it was left; the colour scheme follows the system. While the first-run guide asks for the position (`picking`) a click on the map is a place (`pick`), and the place the guide
// holds (`pin`) has a marker, which the map flies to when it was typed and not clicked. An object or an item of ours (`own`) has a marker that can be dragged: where it is dropped is its new place (`move`).
// A right-click on the map (a long press on a touch screen) opens a menu where the pointer is (composables/useMapMenu.ts, components/MapMenu.vue): the place under it to copy, Statistics, which opens the statistics card over the map (`stats`, the page's), Monitor, the HF radio's scope as a card (`monitor`, the page's; there only while a radio has a scope), and Replay, which plays back how the stations moved over the last hours, the live markers, tracks and route giving way to it while it is open (`replay`, the page's: composables/useMapReplay.ts, components/ReplayBar.vue). Round our own station runs the ALOHA circle, a thin dashed line under the markers at the radius the daemon worked out (lib/alohacircle.ts); a pointer resting on it gets its radius as the title of the map. The selected station, when it is a digipeater of the Nearby tab that gave
// a range (PHG or RNG), has a pale circle of that range under the markers too (lib/rangecircles.ts), one at a time; when such a station is picked the map fits itself to the whole circle instead of flying to the point (composables/useMapFollow.ts). While the beacon is mobile and the GPS has a fix, a button Follow me keeps the map centred on the fix (composables/useFollowMe.ts).
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { GeoJSONSource, Map as MapLibreMap, Marker } from "maplibre-gl";
import { t } from "@/i18n";
import MapAttribution from "@/components/MapAttribution.vue";
import { archivesPresent, loadMapEngine } from "@/lib/basemap";
import { MAX_ZOOM, OPEN_ZOOM } from "@/lib/basemapstyle";
import { useBasemapStyle } from "@/composables/useBasemapStyle";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useMapCircles } from "@/composables/useMapCircles";
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
import { rangeCircleOf } from "@/lib/nearby";
import { heardDirectRecently } from "@/lib/routes";
import { routeFeatures } from "@/lib/routeline";
import { addRouteLayers, ROUTE_SOURCE } from "@/lib/routelayers";
import { addTrackLayers, setTrackData } from "@/lib/tracklayers";
import { placePin } from "@/lib/pinmarker";
import MapMenu from "@/components/MapMenu.vue";
import { useMapMenu } from "@/composables/useMapMenu";
import ReplayBar from "@/components/ReplayBar.vue";
import TrafficCard from "@/components/TrafficCard.vue";
import { useTrafficMap } from "@/composables/useTrafficMap";
import { useMapReplay } from "@/composables/useMapReplay";
import { hasPosition } from "@/lib/stations";
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
    /** The replay is open (the page's: Esc closes it with the cards). */
    replay?: boolean;
  }>(),
  { others: () => [], picking: false, pin: null, replay: false },
);
const emit = defineEmits<{
  select: [call: string | null, multi?: boolean];
  download: [];
  pick: [at: Home];
  move: [call: string, lat: number, lon: number];
  stats: [];
  monitor: [];
  replay: [open: boolean];
}>();
const page = useDaemonContext();

const root = ref<HTMLElement | null>(null);
const host = ref<HTMLElement | null>(null);
const card = useClearOfCard(root, host);
const selectedCall = (): string | null => props.selected;
const stationOf = (call: string): StationRow | undefined => page.stations.value.get(call);
const circles = useMapCircles(() => map, host, selectedCall);
const labelControls = useMapControlLabels(host);
useResized(host, () => map?.resize());
const { following, canFollow, followAt, release } = useFollowMe(page.gps);
const { files, engineFailed, unreadable, note, offerDownload, onMapError } = useMapNote(page);
const basemap = useBasemapStyle(
  page,
  files,
  unreadable,
  () => map,
  () => gone,
); // the style from the files the daemon has, set again when they or the colour scheme change
const traffic = useTrafficMap(() => map, page); // the ships and the aircraft (ais/enabled, adsb/enabled): layers of their own under the station markers, and the card of the one clicked
const placed = new Map<string, Placed>();
let map: MapLibreMap | null = null;
let engine: Awaited<ReturnType<typeof loadMapEngine>> | null = null;
let centred = true; // the view is the one of the last visit, or has been set to where we are
let gone = false;
let pinMarker: Marker | null = null;
let hover: HoverCard | null = null;
let clicked = false; // the pin moved because the map was clicked: the map is where the user is looking already
let picks = 0;
const markerPick = ref<Focus | null>(null); // the marker clicked last: the map fits itself to a digipeater's range circle when it is one (composables/useMapFollow.ts)

/** The tracks are drawn again once a minute, and when a station changes; the fading is in steps that wide anyway. */
const minute = computed(() => Math.floor(page.now.value / 60_000));

function drawRoute(): void {
  const row = props.selected === null ? undefined : page.stations.value.get(props.selected);
  void map?.getSource<GeoJSONSource>(ROUTE_SOURCE)?.setData(routeFeatures(row, page.stations.value, page.home.value));
}

function addLayers(): void {
  if (!map) return;
  circles.add(map); // (first: under the tracks and the route)
  addTrackLayers(map);
  drawTracks();
  addRouteLayers(map, routeFeatures(undefined, page.stations.value, null));
  drawRoute();
  traffic.add();
  replay.add(); // (last: over the live layers, which it hides while it plays)
}

/** The stations that are drawn: with a position and not past their timeout (a station whose card is open is drawn, with its track, whatever its timeout). */
function drawn(): StationRow[] {
  return [...page.stations.value.values()].filter((row) => hasPosition(row) && (isOpen(row.call) || !timedOut(page.aging.value, row, page.now.value)));
}

function drawTracks(): void {
  if (map) setTrackData(map, drawn(), openCalls(), page.now.value, page.aging.value);
}

function makePlaced(call: string): Placed | null {
  if (!map || !engine) return null;
  const dom = buildMarkerDom();
  dom.root.addEventListener("click", (event: MouseEvent) => {
    event.stopPropagation(); // not a click on the map, which lets go of the selection
    hover?.hide();
    emit("select", call, event.ctrlKey || event.metaKey); // (Ctrl, or Cmd on a Mac, adds the card to the open ones)
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

const mapMenu = useMapMenu(host, () => ({ map, hover }));
const menuEvents = { close: () => mapMenu.close(), stats: () => emit("stats"), monitor: () => emit("monitor"), replay: () => emit("replay", true) };
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
  const view = readView();
  centred = view !== null;
  const home = view ?? (page.home.value ? { ...page.home.value, zoom: OPEN_ZOOM } : WORLD_VIEW);
  centred ||= page.home.value !== null;
  try {
    map = new engine.Map({
      container: host.value,
      style: basemap.first(),
      center: [home.lon, home.lat],
      zoom: home.zoom,
      maxZoom: MAX_ZOOM,
      dragRotate: false,
      pitchWithRotate: false,
      attributionControl: false, // the page draws its own: a small (i), closed until clicked
    });
  } catch {
    engineFailed.value = true; // a browser without WebGL
    return;
  }
  map.touchZoomRotate.disableRotation();
  map.addControl(new engine.NavigationControl({ showCompass: false }), "top-left");
  labelControls();
  map.on("style.load", addLayers);
  traffic.listen(map);
  circles.listen(map);
  map.on("movestart", () => hover?.hide());
  map.on("dragstart", release); // (a drag by the person; the map's own easing is none)
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

watch([() => [...page.stations.value.values()], () => [props.selected, props.others, page.aging.value.defaultMin]], () => {
  syncMarkers();
  drawTracks();
  drawRoute();
});
watch(() => page.now.value, syncMarkers);
watch(minute, drawTracks);
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
onMounted(() => {
  if (root.value) hover = new HoverCard(root.value, stationOf, () => page.now.value, page.radiosNamed);
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
  <!-- the note is beside the map and not in it: the map is a layer of its own, under the first-run guide, and the note is above the guide. The page's own classes are on the root and never on the
       map's box, whose classes MapLibre sets (`maplibregl-map`, which clips the markers to the box): a class bound by Vue there is written as the whole class list and took MapLibre's away. -->
  <div ref="root" class="stationmap" :class="{ 'map-picking': props.picking, replaying: props.replay }" v-on="mapMenu.on">
    <div ref="host" class="mapbox" role="application" :aria-label="t('map.label')"></div>
    <MapMenu v-if="mapMenu.menu.value" :key="mapMenu.key.value" v-bind="mapMenu.menu.value" :trigger="host" v-on="menuEvents" />
    <ReplayBar v-if="props.replay" :replay="replay.clock" @close="emit('replay', false)" />
    <TrafficCard
      v-if="traffic.picked.value"
      :pick="traffic.picked.value"
      :ship="traffic.ship.value"
      :aircraft="traffic.aircraft.value"
      :now="page.now.value"
      @close="traffic.close"
    />
    <button v-if="canFollow" class="btn followme" :class="{ primary: following }" type="button" :aria-pressed="following" @click="following = !following">
      {{ t("map.follow_me") }}
    </button>
    <MapAttribution />
  </div>
  <div v-if="note" class="mapnote" role="status">
    <div class="mapnote-box">
      <span>{{ t(note) }}</span>
      <button v-if="offerDownload" class="btn" type="button" @click="emit('download')">{{ t("map.download") }}</button>
    </div>
  </div>
</template>
