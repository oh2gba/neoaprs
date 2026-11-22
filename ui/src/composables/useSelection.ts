// The stations whose cards are open. A click on a marker or table row opens one card; with Ctrl
// (Cmd on a Mac) it adds or removes that station's card (`multi`). The newest card is `selected`
// (its route is drawn, its Esc closes first), the others are `others`. `capacity` limits the open
// cards (1 on a phone, 2 on a tablet, by window height on a desktop; moved cards count): the
// oldest closes first. A table row also flies the map to the station (`focus` counts up so the
// same station twice flies twice) unless it is added to the others. A station the daemon no
// longer has is let go. A card can be pinned (`pinned`, only where `pinsOn`): it stays open past
// another pick, Esc, Close all and the oldest-first closing; only its cross (`close`) closes and
// unpins it. Pinned cards come back with the page and open once the daemon has sent the
// stations (`ready`).
import { computed, ref, watch, type Ref } from "vue";
import type { Focus } from "@/lib/mapview";
import type { Command, StationRow } from "@/protocol/protocol";

export interface Pins {
  pinned?: Ref<string[]>;
  pinsOn?: Readonly<Ref<boolean>>;
  /** The daemon has sent the stations: a pinned call it does not have is dropped. */
  ready?: Readonly<Ref<boolean>>;
}

export function useSelection(
  stations: Readonly<Ref<ReadonlyMap<string, StationRow>>>,
  send: (command: Command) => boolean,
  capacity?: Readonly<Ref<number>>,
  pins: Pins = {},
) {
  const open = ref<string[]>([]);
  const pinned = pins.pinned ?? ref<string[]>([]);
  const isPinned = (call: string): boolean => (pins.pinsOn?.value ?? true) && pinned.value.includes(call);
  const focus = ref<Focus | null>(null);
  // A station was picked and not let go: its route is drawn. Esc and a click on the map end it.
  const active = ref(true);
  let asked = 0;
  const most = (): number => Math.max(1, capacity?.value ?? 1);

  const selected = computed<string | null>({
    get: () => open.value.at(-1) ?? null,
    set: (call) => (open.value = call === null ? [] : [call]),
  });
  const others = computed(() => open.value.slice(0, -1));
  /**
   * What the map marks: the selected station and the others; after Esc the pinned cards are all
   * "others".
   */
  const mapSelected = computed(() => (active.value ? selected.value : null));
  const mapOthers = computed(() => (active.value ? others.value : open.value));
  const rows = computed(() => open.value.flatMap((call) => stations.value.get(call) ?? []));
  const row = computed(() => (selected.value === null ? null : (stations.value.get(selected.value) ?? null)));

  /**
   * A moved card leaves its row slot empty but counts against `capacity`; the oldest unpinned card
   * closes.
   */
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

  /**
   * Open this station's card alone, or with `multi` add or remove it; return whether it is open.
   */
  function pick(call: string, multi = false): boolean {
    active.value = true;
    const kept = open.value.filter((one) => one !== call && isPinned(one));
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

  function pickFromTable(call: string, multi = false): void {
    const opened = pick(call, multi);
    if (opened && !(multi && most() > 1)) focus.value = { call, n: ++asked };
  }

  function close(call: string): void {
    open.value = open.value.filter((one) => one !== call);
    if (pinned.value.includes(call)) pinned.value = pinned.value.filter((one) => one !== call);
  }

  /** The row is too wide: close the oldest card that is not pinned, never the newest. */
  function closeOldest(): void {
    const oldest = open.value.slice(0, -1).find((call) => !isPinned(call));
    if (oldest !== undefined) open.value = open.value.filter((call) => call !== oldest);
  }

  /**
   * Esc and Close all: close every unpinned card and clear the marking; return whether any was
   * open.
   */
  function closeAll(): boolean {
    const staying = open.value.filter(isPinned);
    const some = staying.length < open.value.length || (active.value && staying.length > 0);
    open.value = staying;
    active.value = false;
    return some;
  }

  function pin(call: string, on: boolean): void {
    if (on && open.value.includes(call) && !pinned.value.includes(call)) pinned.value = [...pinned.value, call];
    else if (!on) pinned.value = pinned.value.filter((one) => one !== call);
  }

  function forget(call: string): void {
    if (send({ cmd: "forget_station", call })) close(call);
  }

  return {
    selected,
    others,
    mapSelected,
    mapOthers,
    open,
    rows,
    focus,
    row,
    pinned,
    pin,
    pick,
    pickFromTable,
    close,
    closeOldest,
    closeAll,
    forget,
  };
}

/**
 * Drop cards of stations the daemon does not have; once it has sent them, open the returning pinned
 * cards.
 */
function followStations(
  stations: Readonly<Ref<ReadonlyMap<string, StationRow>>>,
  open: Ref<string[]>,
  pinned: Ref<string[]>,
  pins: Pins,
): void {
  const told = (): boolean => pins.ready?.value ?? true;
  watch(
    () => [
      told(),
      ...open.value.filter((call) => !stations.value.has(call)),
      ...pinned.value.filter((call) => !stations.value.has(call)),
    ],
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
