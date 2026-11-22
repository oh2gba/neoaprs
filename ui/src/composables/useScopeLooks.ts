// Who is looking at a radio's scope, counted in one place (composables/useRadioAsks.ts, as a Sound card radio's receive level is): the box of a radio in Settings (composables/useHfScope.ts) and the monitor card over the map
// (components/MonitorCard.vue) each say `look` while they show the picture, and of which radio, and the page asks the daemon for that radio's rows (`radio_scope`) while at least one does, this page is in front, the radio has a
// scope now (it is on, its type has one and its modem the interface that makes the rows) and the socket is open. Each radio looked at is asked for at once, in frames that name their radio, so that the page keeps each
// radio's rows apart (composables/useScopeRows.ts). Here too is the radio the monitor card shows: the one chosen in the map's menu, remembered by this browser, else the one it showed, else the first that has a scope. The card leaves its radio only when that radio can have no scope (it is
// off, removed, or of a type without one): while its modem is without the interface for a moment (started again), the card stays on it.
import { computed, type Ref } from "vue";
import { usePersistedNumber } from "@/composables/usePersisted";
import { useRadioAsks } from "@/composables/useRadioAsks";
import type { Connection } from "@/lib/hub";
import { keepList } from "@/lib/keeplist";
import type { RadioId } from "@/lib/radios";
import type { Command, RadioRow } from "@/protocol/protocol";

/** The parts the page gives: the topic `radios` (no radio has a scope before it is told). */
export interface ScopeParts {
  radios?: Readonly<Ref<ReadonlyMap<string, RadioRow> | null>>;
}

export interface ScopeLooks {
  /** the radios that have a scope to show now, in the order of their boxes */
  radios: Readonly<Ref<readonly RadioId[]>>;
  /** some radio has a scope to show */
  available: Readonly<Ref<boolean>>;
  /** whether that radio has a scope to show now */
  has: (radio: RadioId) => boolean;
  /** the radios whose rows are asked for, in the order of their boxes: someone looks at each, the page is in front and the socket is open */
  asked: Readonly<Ref<readonly RadioId[]>>;
  /** the rows of some radio are asked for */
  wanted: Readonly<Ref<boolean>>;
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
  connection: Readonly<Ref<Connection>>,
  visible: Readonly<Ref<boolean>>,
  parts: ScopeParts = {},
): ScopeLooks {
  const radios = computed<readonly RadioId[]>((old) => {
    const topic = parts.radios?.value ?? null;
    const ids =
      topic === null
        ? []
        : [...topic.values()]
            .filter(withScope)
            .sort((a, b) => a.position - b.position || a.id - b.id)
            .map((row) => row.id);
    return keepList(old, ids);
  });
  const has = (radio: RadioId): boolean => radios.value.includes(radio);
  const first = (): RadioId | null => radios.value[0] ?? null;

  const { asked, lookers, look: looks } = useRadioAsks("radio_scope", send, connection, visible, () => radios.value);

  /** The radio can have a scope (before the topic `radios` is told: it has one now). */
  const keeps = (radio: RadioId): boolean => (parts.radios?.value ? canHave(parts.radios.value, radio) : has(radio));
  const chosen = usePersistedNumber("monitorradio", 0, 0, Number.MAX_SAFE_INTEGER);
  const monitor = computed<RadioId | null>((old) => {
    if (radios.value.length === 0) return null;
    for (const radio of [chosen.value, old ?? null]) if (radio !== null && keeps(radio)) return radio;
    return first();
  });

  return {
    radios,
    available: computed(() => radios.value.length > 0),
    has,
    asked,
    wanted: computed(() => asked.value.length > 0),
    lookers,
    monitor,
    showOnMonitor: (radio) => void (chosen.value = radio),
    look: (looking, radio = first) => looks(looking, radio),
  };
}
