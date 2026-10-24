// The stations whose cards are open: a click on a marker or on a row of the table opens one card (the open ones go); with Ctrl held (Cmd on a Mac) the click adds the card of that station to the open ones, or closes it when it is open already
// (`multi`). The newest card is the selected station (`selected`: the one whose route is drawn, whose Esc closes first); the others are `others`. How many cards may be open is `capacity` (1 on a phone, 2 on a tablet, by the height of the window
// on a desktop, moved cards count too): the oldest closes first when a new one would be one too many, and a window that gets smaller closes the oldest. A row of the table also flies the map to the station (`focus`, which counts up so that the same station picked
// twice flies twice), unless it is added to the others (the map stays where the user has it). A station the daemon no longer has (forgotten, pruned) is let go of.
import { computed, ref, watch, type Ref } from "vue";
import type { Focus } from "@/lib/mapview";
import type { Command, StationRow } from "@/protocol/protocol";

export function useSelection(stations: Readonly<Ref<ReadonlyMap<string, StationRow>>>, send: (command: Command) => boolean, capacity?: Readonly<Ref<number>>) {
  const open = ref<string[]>([]); // the calls of the open cards, the oldest first
  const focus = ref<Focus | null>(null);
  let asked = 0;
  const most = (): number => Math.max(1, capacity?.value ?? 1);

  /** The newest card's station; assigning a call makes it the only open one, null closes all. */
  const selected = computed<string | null>({
    get: () => open.value.at(-1) ?? null,
    set: (call) => (open.value = call === null ? [] : [call]),
  });
  const others = computed(() => open.value.slice(0, -1));
  const rows = computed(() => open.value.flatMap((call) => stations.value.get(call) ?? []));
  const row = computed(() => (selected.value === null ? null : (stations.value.get(selected.value) ?? null)));

  /** A card the user has moved stays where it is and leaves its place in the row empty (the others never move for it), so it counts against `capacity` like the others: when a new one would be one too many the oldest closes. */
  const trim = (): void => {
    const drop = open.value.length - most();
    if (drop > 0) open.value = open.value.slice(drop);
  };
  watch(most, trim);
  watch(
    () => open.value.filter((call) => !stations.value.has(call)),
    (gone) => {
      if (gone.length > 0) open.value = open.value.filter((call) => !gone.includes(call));
    },
  );

  /** A click on a marker or a row: this station's card alone; with `multi`, added to the open ones (or closed, when it is one of them). Returns whether the station's card is open after it. */
  function pick(call: string, multi = false): boolean {
    if (!multi || most() < 2) {
      open.value = [call];
      return true;
    }
    if (open.value.includes(call)) {
      open.value = open.value.filter((one) => one !== call);
      return false;
    }
    open.value = [...open.value, call];
    trim();
    return true;
  }

  /** A station picked in the table: selected, and the map flies to it (not when it is added to the others). */
  function pickFromTable(call: string, multi = false): void {
    const opened = pick(call, multi);
    if (opened && !(multi && most() > 1)) focus.value = { call, n: ++asked };
  }

  /** The cross of one card. */
  function close(call: string): void {
    open.value = open.value.filter((one) => one !== call);
  }

  /** The row of cards is wider than the map has room for: the oldest card closes, but never the only one. */
  function closeOldest(): void {
    if (open.value.length > 1) open.value = open.value.slice(1);
  }

  /** Esc, and Close all: every card goes, and with them the marking of the markers and the rows; whether there was one. */
  function closeAll(): boolean {
    const some = open.value.length > 0;
    open.value = [];
    return some;
  }

  /** The Forget of a station's card: the daemon forgets it, and its card is closed. */
  function forget(call: string): void {
    if (send({ cmd: "forget_station", call })) close(call);
  }

  return { selected, others, open, rows, focus, row, pick, pickFromTable, close, closeOldest, closeAll, forget };
}
