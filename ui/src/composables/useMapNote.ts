// The note over the map: from which map files the daemon has, whether the engine loaded and
// which sources it could not open, the id of the message shown when the map cannot be drawn well
// (or none), and whether it has the button to where the map is made.
import { computed, ref } from "vue";
import type { MessageId } from "@/i18n/catalogue";
import { BASE_SOURCE, WORLD_SOURCE } from "@/lib/basemapstyle";
import type { DaemonContext } from "@/composables/useDaemonContext";

/** `page`: whether the first-run guide is open and whether a base map download runs. */
export function useMapNote(page: Pick<DaemonContext, "guide" | "map">) {
  const files = ref({ detail: false, world: false });
  // The engine could not be loaded, or the browser has no WebGL.
  const engineFailed = ref(false);
  // Sources whose archive the engine could not open (not a PMTiles archive).
  const unreadable = ref<string[]>([]);

  /**
   * The note over the map; the no-detail line is left out while the guide is open or a download
   * runs.
   */
  const note = computed<MessageId | "">(() => {
    if (engineFailed.value) return "map.note.no_engine";
    const { detail, world } = files.value;
    if (!detail && !world) return "map.note.no_basemap";
    if ((!detail || unreadable.value.includes(BASE_SOURCE)) && (!world || unreadable.value.includes(WORLD_SOURCE)))
      return "map.note.unreadable";
    return !detail && !page.guide.open && page.map.value?.state !== "downloading" ? "map.note.no_detail" : "";
  });
  /** Whether the note has the button to where the map is made (not over the guide). */
  const offerDownload = computed(
    () =>
      !page.guide.open &&
      (note.value === "map.note.no_basemap" ||
        note.value === "map.note.no_detail" ||
        (note.value === "map.note.unreadable" && files.value.detail)),
  );

  /**
   * A source whose archive cannot be opened (an error with no tile: the header or directory
   * failed).
   */
  function onMapError(event: unknown): void {
    const { sourceId, tile } = event as { sourceId?: string; tile?: unknown };
    if (
      sourceId &&
      tile === undefined &&
      [BASE_SOURCE, WORLD_SOURCE].includes(sourceId) &&
      !unreadable.value.includes(sourceId)
    ) {
      unreadable.value = [...unreadable.value, sourceId];
    }
  }

  return { files, engineFailed, unreadable, note, offerDownload, onMapError };
}
