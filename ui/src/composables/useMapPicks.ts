// The places that are picked with a click on the map: the first-run guide's (it asks while its position step is on), the Beacon tab's Pick on the map, and the Objects tab's. A click on the map is a place for the guide while it asks for one, else for the Beacon
// tab, else for the form of an object. `pickingTab` is a place that a tab asked for (the guide's own is its business): a phone shows the map for it (composables/useLayout.ts) and `cancel` ends it.
import { computed } from "vue";
import { usePositionPick } from "@/composables/usePositionPick";
import type { OwnObjectsView } from "@/composables/useOwnObjects";
import type { SetupGuide } from "@/composables/useSetupGuide";
import type { Home } from "@/lib/mapview";

export function useMapPicks(guide: SetupGuide, objects: OwnObjectsView) {
  const stationPick = usePositionPick();
  const pickingTab = computed(() => stationPick.picking.value || objects.picking);

  function onPick(at: Home): void {
    if (guide.picking) guide.place(at.lat, at.lon);
    else if (stationPick.picking.value) stationPick.place(at.lat, at.lon);
    else objects.place(at.lat, at.lon);
  }

  function cancel(): void {
    stationPick.picking.value = false;
    objects.placing = false;
  }

  return { stationPick, pickingTab, onPick, cancel };
}
