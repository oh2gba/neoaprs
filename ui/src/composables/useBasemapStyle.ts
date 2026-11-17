// The style of the map (components/StationMap.vue) from the base map files the daemon serves: the addresses of the detailed map and the world map, made again when the daemon makes the files again (their dates change: the
// addresses then carry a count, so that the reader of the archives starts afresh), and the style set again when those addresses or the colour scheme change.
import { computed, watch, type Ref } from "vue";
import type { Map as MapLibreMap, StyleSpecification } from "maplibre-gl";
import type { DaemonContext } from "@/composables/useDaemonContext";
import { archiveUrl, archivesPresent, glyphsUrl } from "@/lib/basemap";
import { BASEMAP_FILE, WORLD_FILE, basemapStyle, type Archives } from "@/lib/basemapstyle";
import { filesKey } from "@/lib/mapfetch";

interface Files {
  detail: boolean;
  world: boolean;
}

export function useBasemapStyle(
  page: Pick<DaemonContext, "map" | "dark">,
  files: Ref<Files>,
  unreadable: Ref<string[]>,
  mapOf: () => MapLibreMap | null,
  gone: () => boolean,
) {
  /** Changes when the map files on the daemon are other ones (their dates); null until the daemon has told. */
  const mapFiles = computed(() => filesKey(page.map.value));
  let generation = 0; // counts the times the files were made again: the addresses carry it, so that the reader of the archives starts afresh
  let seenKey: string | null = mapFiles.value;
  let shown = ""; // the addresses the style on the map was made with

  const archives = (): Archives => ({
    detail: files.value.detail ? archiveUrl(BASEMAP_FILE, generation > 0 ? String(generation) : "") : null,
    world: files.value.world ? archiveUrl(WORLD_FILE, generation > 0 ? String(generation) : "") : null,
  });
  const styleFor = (dark: boolean): StyleSpecification => basemapStyle(archives(), dark, glyphsUrl());

  /** The daemon has other files: ask which it has, and set the style again if the addresses are other ones. */
  async function refresh(): Promise<void> {
    files.value = await archivesPresent();
    const map = mapOf();
    if (gone() || !map) return;
    const now = JSON.stringify(archives());
    if (now === shown) return;
    shown = now;
    unreadable.value = [];
    map.setStyle(styleFor(page.dark.value));
  }

  /** The style the map is made with; the addresses it was made of are remembered. */
  function first(): StyleSpecification {
    shown = JSON.stringify(archives());
    return styleFor(page.dark.value);
  }

  watch(mapFiles, (key) => {
    if (key === null || key === seenKey) return;
    if (seenKey !== null) generation += 1; // (the first word from the daemon is not a change)
    seenKey = key;
    void refresh();
  });
  watch(page.dark, (dark) => mapOf()?.setStyle(styleFor(dark)));

  return { first };
}
