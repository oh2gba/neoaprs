// The station cards as the page runs them: the stations whose cards are open (composables/useSelection.ts, as many as the size of the window has room for), Esc, which closes them all, and the clicks of the map and of the table. A click on a marker is its card
// alone, or with Ctrl (Cmd) held added to the open ones; the map itself lets go of all of them. A click on a row of the table does the same, and a phone, which shows the tab or the map, shows the map with the card.
import type { Ref } from "vue";
import { useCardEsc } from "@/composables/useCardEsc";
import type { Layout } from "@/composables/useLayout";
import { useSelection } from "@/composables/useSelection";
import type { Command, StationRow } from "@/protocol/protocol";

export function useStationCards(
  stations: Readonly<Ref<ReadonlyMap<string, StationRow>>>,
  send: (command: Command) => boolean,
  layout: Layout,
  blocked: () => boolean,
) {
  const cards = useSelection(stations, send, layout.capacity);
  useCardEsc(cards.closeAll, blocked);

  function onMarker(call: string | null, multi = false): void {
    if (call === null) cards.closeAll();
    else cards.pick(call, multi);
  }

  function onRow(call: string, multi = false): void {
    cards.pickFromTable(call, multi);
    if (layout.phone.value) layout.showMap();
  }

  return { ...cards, onMarker, onRow };
}
