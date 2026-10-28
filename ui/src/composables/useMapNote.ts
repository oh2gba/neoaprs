// The note over the map (components/StationMap.vue): which of the two map files the daemon has, whether the engine could be loaded, and which sources the engine could not open an archive of. From these: the id of the message that stands over the map when
// it cannot be drawn well (or none) and whether it has the button that goes to where the map is made.
import { computed, ref } from "vue";
import type { MessageId } from "@/i18n/catalogue";
import { BASE_SOURCE, WORLD_SOURCE } from "@/lib/basemapstyle";
import type { MapState } from "@/protocol/protocol";

export function useMapNote(guideOpen: () => boolean, map: () => MapState | null) {
  const files = ref({ detail: false, world: false }); // which of the two files the daemon has
  const engineFailed = ref(false); // the map engine could not be loaded, or the browser has no WebGL
  const unreadable = ref<string[]>([]); // the sources whose archive the engine could not open (a file that is not a PMTiles archive)

  /** What stands over the map: the no-detail line is left out while the first-run guide is open (it makes the detailed map itself) or a download runs. */
  const note = computed<MessageId | "">(() => {
    if (engineFailed.value) return "map.note.no_engine";
    const { detail, world } = files.value;
    if (!detail && !world) return "map.note.no_basemap";
    if ((!detail || unreadable.value.includes(BASE_SOURCE)) && (!world || unreadable.value.includes(WORLD_SOURCE))) return "map.note.unreadable";
    return !detail && !guideOpen() && map()?.state !== "downloading" ? "map.note.no_detail" : "";
  });
  /** ... and whether it has the button that goes to where the map is made (not over the guide, which has its own quiet line about the map). */
  const offerDownload = computed(
    () =>
      !guideOpen() &&
      (note.value === "map.note.no_basemap" || note.value === "map.note.no_detail" || (note.value === "map.note.unreadable" && files.value.detail)),
  );

  /** A source whose archive cannot be opened (the error has no tile: it is the file's header or directory that failed) is a map file that cannot be drawn. */
  function onMapError(event: unknown): void {
    const { sourceId, tile } = event as { sourceId?: string; tile?: unknown }; // (the engine adds the source and the tile to the error event it fires)
    if (sourceId && tile === undefined && [BASE_SOURCE, WORLD_SOURCE].includes(sourceId) && !unreadable.value.includes(sourceId)) {
      unreadable.value = [...unreadable.value, sourceId];
    }
  }

  return { files, engineFailed, unreadable, note, offerDownload, onMapError };
}
