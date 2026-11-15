// Who is looking at a radio's scope, counted in one place: the box of a radio in Settings (composables/useHfScope.ts) and the monitor card over the map (components/MonitorCard.vue) each say `look` while they show the picture, and of
// which radio, and the page asks the daemon for that radio's rows (`radio_scope`) while at least one does, this page is in front, the radio has a scope now (it is on, its type has one and its modem the interface that makes
// the rows) and the socket is open; asked again when the socket was open anew, since the daemon forgets a page that left. Nobody looking, no rows. A frame of the rows does not name its radio, so the page asks for one
// radio's at a time: the one the pane looks at that began to look last (the others show no rows until it is theirs again), and the page's memory of the rows is that radio's (composables/useScopeRows.ts). Here too is the
// radio the monitor card shows: the one chosen in the map's menu, remembered by this browser, else the one it showed, else the first that has a scope. The card leaves its radio only when that radio can have no scope (it is
// off, removed, or of a type without one): while its modem is without the interface for a moment (started again), the card stays on it.
import { computed, onBeforeUnmount, shallowRef, watch, type Ref } from "vue";
import { usePersistedNumber } from "@/composables/usePersisted";
import { rowsRadio } from "@/composables/useScopeRows";
import type { Connection } from "@/lib/hub";
import type { RadioId } from "@/lib/radios";
import { HF_ID } from "@/lib/radiosides";
import type { ScopeMemory } from "@/lib/scopememory";
import type { Command, RadioRow, TncState } from "@/protocol/protocol";

/** The parts the page gives besides those of before: the topic `radios` (without it, or before it is told, the HF radio of before has the scope the topic `hf` says), and the page's memory of the rows. */
export interface ScopeParts {
  radios?: Readonly<Ref<ReadonlyMap<string, RadioRow> | null>>;
  rows?: ScopeMemory;
}

export interface ScopeLooks {
  /** the radios that have a scope to show now, in the order of their boxes */
  radios: Readonly<Ref<readonly RadioId[]>>;
  /** some radio has a scope to show */
  available: Readonly<Ref<boolean>>;
  /** whether that radio has a scope to show now */
  has: (radio: RadioId) => boolean;
  /** the radio whose rows are asked for: someone looks at it, the page is in front and the socket is open; null while none is */
  asked: Readonly<Ref<RadioId | null>>;
  /** the rows of some radio are asked for */
  wanted: Readonly<Ref<boolean>>;
  /** the radio whose rows the page keeps: the one asked for last, and before any the first that has a scope */
  rowsOf: Readonly<Ref<RadioId | null>>;
  /** how many panes are looking now */
  lookers: Readonly<Ref<number>>;
  /** the radio the monitor card shows (it may be without its scope for a moment); null while no radio has a scope */
  monitor: Readonly<Ref<RadioId | null>>;
  /** The monitor card shows that radio (the map's menu). */
  showOnMonitor: (radio: RadioId) => void;
  /** A pane, from its setup on: it looks at `radio` (the first radio with a scope when it names none) while `looking` is true and stops when it goes. */
  look: (looking: () => boolean, radio?: () => RadioId | null) => void;
}

/** A radio that can have a scope: on, not removed, and of a type that has one. */
const scoped = (row: RadioRow): boolean => row.enabled && !row.removed && row.can.scope;
/** A radio that has a scope to show now: one that can, and its modem has the interface. */
const withScope = (row: RadioRow): boolean => scoped(row) && row.modem?.scope === true;
/** That radio of the topic `radios` can have a scope. */
const canHave = (topic: ReadonlyMap<string, RadioRow>, radio: RadioId): boolean => [...topic.values()].some((row) => row.id === radio && scoped(row));

export function useScopeLooks(
  send: (command: Command) => boolean,
  hf: Readonly<Ref<TncState | null>>,
  connection: Readonly<Ref<Connection>>,
  visible: Readonly<Ref<boolean>>,
  parts: ScopeParts = {},
): ScopeLooks {
  const radios = computed<readonly RadioId[]>((old) => {
    const topic = parts.radios?.value ?? null;
    const ids =
      topic === null
        ? hf.value?.modem?.scope === true
          ? [HF_ID]
          : []
        : [...topic.values()]
            .filter(withScope)
            .sort((a, b) => a.position - b.position || a.id - b.id)
            .map((row) => row.id);
    return old !== undefined && old.length === ids.length && ids.every((id, i) => id === old[i]) ? old : ids;
  });
  const has = (radio: RadioId): boolean => radios.value.includes(radio);
  const first = (): RadioId | null => radios.value[0] ?? null;

  /** The panes looking now, the one that began last at the end. */
  const looking = shallowRef<readonly (() => RadioId | null)[]>([]);
  const asked = computed<RadioId | null>(() => {
    if (!visible.value || connection.value !== "open") return null;
    for (let i = looking.value.length - 1; i >= 0; i--) {
      const radio = looking.value[i]();
      if (radio !== null && has(radio)) return radio;
    }
    return null;
  });
  // at once, not on the next tick: a pane that looks from its first moment asks in that moment
  // (a socket that is closed says no to nothing: the daemon forgets the page by itself)
  watch(
    asked,
    (radio, was) => {
      if (was !== null && was !== undefined && connection.value === "open") send({ cmd: "radio_scope", radio: was, on: false });
      if (radio !== null) send({ cmd: "radio_scope", radio, on: true });
    },
    { flush: "sync" },
  );

  const last = shallowRef<RadioId | null>(null);
  watch(asked, (radio) => radio !== null && void (last.value = radio), { flush: "sync" });
  const rowsOf = computed(() => last.value ?? first());
  const held = parts.rows === undefined ? undefined : rowsRadio(parts.rows);
  if (held !== undefined) watch(rowsOf, (radio) => void (held.value = radio), { immediate: true, flush: "sync" });

  /** The radio can have a scope (before the topic `radios` is told: it has one now). */
  const keeps = (radio: RadioId): boolean => (parts.radios?.value ? canHave(parts.radios.value, radio) : has(radio));
  const chosen = usePersistedNumber("monitorradio", 0, 0, Number.MAX_SAFE_INTEGER);
  const monitor = computed<RadioId | null>((old) => {
    if (radios.value.length === 0) return null;
    for (const radio of [chosen.value, old ?? null]) if (radio !== null && keeps(radio)) return radio;
    return first();
  });

  function look(looks: () => boolean, radio: () => RadioId | null = first): void {
    const pane = (): RadioId | null => radio(); // (its own, so that two panes of the same radio are two)
    let now = false;
    const set = (on: boolean): void => {
      if (on === now) return;
      now = on;
      looking.value = on ? [...looking.value, pane] : looking.value.filter((other) => other !== pane);
    };
    const stop = watch(looks, set, { immediate: true, flush: "sync" });
    onBeforeUnmount(() => {
      stop();
      set(false);
    });
  }
  return {
    radios,
    available: computed(() => radios.value.length > 0),
    has,
    asked,
    wanted: computed(() => asked.value !== null),
    rowsOf,
    lookers: computed(() => looking.value.length),
    monitor,
    showOnMonitor: (radio) => void (chosen.value = radio),
    look,
  };
}
