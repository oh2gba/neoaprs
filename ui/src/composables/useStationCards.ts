// The station cards: the open stations (useSelection, as many as the window has room for), Esc
// closing them all, and the clicks of the map and table. A click on a marker or row opens its
// card alone, or with Ctrl (Cmd) adds it; the map itself lets go of all. A phone shows the map
// with the card. Once none is open, Esc closes the next thing over the map (`alsoClose`). A pinned
// card is kept by none of that: it stays until its cross is clicked and is kept in the browser
// (lib/pinned.ts).
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
  ready?: Readonly<Ref<boolean>>,
  alsoClose: () => boolean = () => false,
) {
  // Where moved cards stand; kept for the session (and with pinned cards), not on a phone.
  const saved = loadPinned();
  const places = ref<Places>(
    Object.fromEntries(
      Object.entries(saved).flatMap(([call, place]) => (place === null ? [] : [[call, place] as const])),
    ),
  );
  const pinned = ref<string[]>(Object.keys(saved));
  const cards = useSelection(stations, send, layout.capacity, {
    pinned,
    pinsOn: computed(() => !layout.phone.value),
    ready,
  });
  watch([pinned, places], () => savePinned(pinned.value, places.value), { deep: true });
  useCardEsc(() => cards.closeAll() || alsoClose(), blocked);

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
