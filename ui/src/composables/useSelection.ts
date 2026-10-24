// The stations whose cards are open: a click on a marker or on a row of the table opens one card (the open ones go); with Ctrl held (Cmd on a Mac) the click adds the card of that station to the open ones, or closes it when it is open already
// (`multi`). The newest card is the selected station (`selected`: the one whose route is drawn, whose Esc closes first); the others are `others`. How many cards may be open is `capacity` (1 on a phone, 2 on a tablet, by the height of the window
// on a desktop, moved cards count too): the oldest closes first when a new one would be one too many, and a window that gets smaller closes the oldest. A row of the table also flies the map to the station (`focus`, which counts up so that the same station picked
// twice flies twice), unless it is added to the others (the map stays where the user has it). A station the daemon no longer has (forgotten, pruned) is let go of.
// A card can be pinned (`pinned`, the calls; where pins are on, that is a tablet and a desktop, `pinsOn`): it stays open when another station is picked, past Esc and Close all, and past the oldest-first closing of a full row; only its cross (`close`) closes it, and unpins it.
// Pinned cards come back with the page (`pinned` is given, from the browser's storage, and they open once the daemon has told the stations, `ready`; one the daemon no longer has is let go of).
import { computed, ref, watch, type Ref } from "vue";
import type { Focus } from "@/lib/mapview";
import type { Command, StationRow } from "@/protocol/protocol";

export interface Pins {
  /** The calls of the pinned cards, in the order they were pinned. */
  pinned?: Ref<string[]>;
  /** Whether pins count (a phone's one card is a sheet: no). */
  pinsOn?: Readonly<Ref<boolean>>;
  /** The daemon has told the stations: a pinned call it does not have is gone. */
  ready?: Readonly<Ref<boolean>>;
}

export function useSelection(
  stations: Readonly<Ref<ReadonlyMap<string, StationRow>>>,
  send: (command: Command) => boolean,
  capacity?: Readonly<Ref<number>>,
  pins: Pins = {},
) {
  const open = ref<string[]>([]); // the calls of the open cards, the oldest first
  const pinned = pins.pinned ?? ref<string[]>([]);
  const isPinned = (call: string): boolean => (pins.pinsOn?.value ?? true) && pinned.value.includes(call);
  const focus = ref<Focus | null>(null);
  const active = ref(true); // a station was picked and not let go of: its route is drawn. Esc and a click on the map end that, also for the pinned cards that stay
  let asked = 0;
  const most = (): number => Math.max(1, capacity?.value ?? 1);

  /** The newest card's station; assigning a call makes it the only open one, null closes all. */
  const selected = computed<string | null>({
    get: () => open.value.at(-1) ?? null,
    set: (call) => (open.value = call === null ? [] : [call]),
  });
  const others = computed(() => open.value.slice(0, -1));
  /** What the map marks: the selected station (whose route it draws) and the others; after Esc or a click on the map the pinned cards that stay are all "others", with no route. */
  const mapSelected = computed(() => (active.value ? selected.value : null));
  const mapOthers = computed(() => (active.value ? others.value : open.value));
  const rows = computed(() => open.value.flatMap((call) => stations.value.get(call) ?? []));
  const row = computed(() => (selected.value === null ? null : (stations.value.get(selected.value) ?? null)));

  /** A card the user has moved stays where it is and leaves its place in the row empty (the others never move for it), so it counts against `capacity` like the others: when a new one would be one too many the oldest closes. A pinned card never closes for that, nor does the newest. */
  const trim = (): void => {
    const excess = open.value.length - most();
    if (excess <= 0) return;
    const closing = new Set(
      open.value
        .slice(0, -1)
        .filter((call) => !isPinned(call))
        .slice(0, excess),
    );
    if (closing.size > 0) open.value = open.value.filter((call) => !closing.has(call));
  };
  watch(most, trim);
  followStations(stations, open, pinned, pins);

  /** A click on a marker or a row: this station's card alone; with `multi`, added to the open ones (or closed, when it is one of them). Returns whether the station's card is open after it. */
  function pick(call: string, multi = false): boolean {
    active.value = true;
    const kept = open.value.filter((one) => one !== call && isPinned(one)); // (the pinned cards stay, and a pinned card picked again is the newest)
    if (!multi || most() < 2) {
      open.value = [...kept, call];
      return true;
    }
    if (open.value.includes(call) && !isPinned(call)) {
      open.value = open.value.filter((one) => one !== call);
      return false;
    }
    open.value = [...open.value.filter((one) => one !== call), call];
    trim();
    return true;
  }

  /** A station picked in the table: selected, and the map flies to it (not when it is added to the others). */
  function pickFromTable(call: string, multi = false): void {
    const opened = pick(call, multi);
    if (opened && !(multi && most() > 1)) focus.value = { call, n: ++asked };
  }

  /** The cross of one card: it closes, pinned or not, and is not pinned any more. */
  function close(call: string): void {
    open.value = open.value.filter((one) => one !== call);
    if (pinned.value.includes(call)) pinned.value = pinned.value.filter((one) => one !== call);
  }

  /** The row of cards is wider than the map has room for: the oldest card that is not pinned closes, but never the newest. */
  function closeOldest(): void {
    const oldest = open.value.slice(0, -1).find((call) => !isPinned(call));
    if (oldest !== undefined) open.value = open.value.filter((call) => call !== oldest);
  }

  /** Esc, and Close all: every card that is not pinned goes, and with them the marking of the markers and the rows; whether there was one. */
  function closeAll(): boolean {
    const staying = open.value.filter(isPinned);
    const some = staying.length < open.value.length || (active.value && staying.length > 0);
    open.value = staying;
    active.value = false;
    return some;
  }

  /** Pins a card, or takes its pin away (it stays open). Only a card that is open can be pinned. */
  function pin(call: string, on: boolean): void {
    if (on && open.value.includes(call) && !pinned.value.includes(call)) pinned.value = [...pinned.value, call];
    else if (!on) pinned.value = pinned.value.filter((one) => one !== call);
  }

  /** The Forget of a station's card: the daemon forgets it, and its card is closed. */
  function forget(call: string): void {
    if (send({ cmd: "forget_station", call })) close(call);
  }

  return { selected, others, mapSelected, mapOthers, open, rows, focus, row, pinned, pin, pick, pickFromTable, close, closeOldest, closeAll, forget };
}

/**
 * The cards and the stations the daemon has: a card (pinned or not) of a station it has not is let go of, and, once it has told them, the pinned cards that came back with the page open, as the oldest cards (and again when the window is wide
 * enough for pins). Before it has told them a pinned card waits.
 */
function followStations(stations: Readonly<Ref<ReadonlyMap<string, StationRow>>>, open: Ref<string[]>, pinned: Ref<string[]>, pins: Pins): void {
  const told = (): boolean => pins.ready?.value ?? true;
  watch(
    () => [told(), ...open.value.filter((call) => !stations.value.has(call)), ...pinned.value.filter((call) => !stations.value.has(call))],
    ([done, ...gone]) => {
      const missing = gone as string[];
      if (done !== true || missing.length === 0) return;
      open.value = open.value.filter((call) => !missing.includes(call));
      pinned.value = pinned.value.filter((call) => !missing.includes(call));
    },
  );
  watch(
    () => told() && (pins.pinsOn?.value ?? true),
    (on) => {
      const back = on ? pinned.value.filter((call) => stations.value.has(call) && !open.value.includes(call)) : [];
      if (back.length > 0) open.value = [...back, ...open.value];
    },
    { immediate: true },
  );
}
