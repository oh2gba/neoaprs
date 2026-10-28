// The station cards as the page runs them: the stations whose cards are open (composables/useSelection.ts, as many as the size of the window has room for), Esc, which closes them all, and the clicks of the map and of the table. A click on a marker is its card
// alone, or with Ctrl (Cmd) held added to the open ones; the map itself lets go of all of them. A click on a row of the table does the same, and a phone, which shows the tab or the map, shows the map with the card.
// Esc closes the statistics card too (`alsoClose`, the page's). A pinned card (a tablet and a desktop) is not let go of by any of that: it has its place over the map and stays until its cross is clicked, and both are kept in this browser (lib/pinned.ts), so it comes back with the page.
import { computed, ref, watch, type Ref } from "vue";
import { useCardEsc } from "@/composables/useCardEsc";
import type { Places } from "@/composables/useCardDrag";
import type { Layout } from "@/composables/useLayout";
import { useSelection } from "@/composables/useSelection";
import { loadPinned, savePinned } from "@/lib/pinned";
import type { Command, StationRow } from "@/protocol/protocol";

export function useStationCards(
  stations: Readonly<Ref<ReadonlyMap<string, StationRow>>>,
  send: (command: Command) => boolean,
  layout: Layout,
  blocked: () => boolean,
  /** The daemon has told the stations (a pinned card of a station it does not have is gone only then). */
  ready?: Readonly<Ref<boolean>>,
  /** What else Esc closes with the cards (the statistics card); true when it closed something. */
  alsoClose: () => boolean = () => false,
) {
  // where the cards the user has moved stand (components/StationCards.vue keeps them in step with the open cards); only for the session, except those of the pinned cards, and not on a phone, whose card is a sheet
  const saved = loadPinned();
  const places = ref<Places>(Object.fromEntries(Object.entries(saved).flatMap(([call, place]) => (place === null ? [] : [[call, place] as const]))));
  const pinned = ref<string[]>(Object.keys(saved));
  const cards = useSelection(stations, send, layout.capacity, { pinned, pinsOn: computed(() => !layout.phone.value), ready });
  watch([pinned, places], () => savePinned(pinned.value, places.value), { deep: true });
  useCardEsc(() => [cards.closeAll(), alsoClose()].some(Boolean), blocked);

  function onMarker(call: string | null, multi = false): void {
    if (call === null) cards.closeAll();
    else cards.pick(call, multi);
  }

  function onRow(call: string, multi = false): void {
    cards.pickFromTable(call, multi);
    if (layout.phone.value) layout.showMap();
  }

  return { ...cards, places, onMarker, onRow };
}
