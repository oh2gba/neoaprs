// Who is looking at a radio's scope, counted in one place (as in useRadioAsks): a radio's box in
// Settings and the monitor card each say `look` while they show the picture, and of which radio.
// The page asks the daemon for that radio's rows (`radio_scope`) while at least one looks, the
// page is in front, the radio has a scope now (on, its type has one, its modem has the interface)
// and the socket is open. Rows arrive in frames naming their radio, so each radio's rows stay
// apart (useScopeRows). The radio the monitor card shows is also here: the one chosen in the
// map's menu (remembered), else the one it showed, else the first with a scope. The card leaves
// its radio only when that radio can have no scope (off, removed, or of a type without one); while
// its modem lacks the interface for a moment, the card stays on it. A pane says how long a
// picture it shows; the radio is asked for the rows of the longest (in whole minutes), and the
// page keeps that much of them (`keep`).
import { computed, type Ref } from "vue";
import { usePersistedNumber } from "@/composables/usePersisted";
import { useRadioAsks } from "@/composables/useRadioAsks";
import type { Connection } from "@/lib/hub";
import { keepList } from "@/lib/keeplist";
import type { RadioId } from "@/lib/radios";
import { askSeconds } from "@/lib/waterfall";
import type { Command, RadioRow } from "@/protocol/protocol";

export interface ScopeParts {
  radios?: Readonly<Ref<ReadonlyMap<string, RadioRow> | null>>;
  /** The page is to keep the radio's rows of the last `ms`. */
  keep?: (radio: RadioId, ms: number) => void;
}

export interface ScopeLooks {
  radios: Readonly<Ref<readonly RadioId[]>>;
  available: Readonly<Ref<boolean>>;
  has: (radio: RadioId) => boolean;
  asked: Readonly<Ref<readonly RadioId[]>>;
  wanted: Readonly<Ref<boolean>>;
  lookers: Readonly<Ref<number>>;
  monitor: Readonly<Ref<RadioId | null>>;
  showOnMonitor: (radio: RadioId) => void;
  /** `reach`: how many ms of the waterfall the pane shows (0: not known yet). */
  look: (looking: () => boolean, radio?: () => RadioId | null, reach?: () => number) => void;
}

const scoped = (row: RadioRow): boolean => row.enabled && !row.removed && row.can.scope;
const withScope = (row: RadioRow): boolean => scoped(row) && row.modem?.scope === true;
const canHave = (topic: ReadonlyMap<string, RadioRow>, radio: RadioId): boolean =>
  [...topic.values()].some((row) => row.id === radio && scoped(row));

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

  const {
    asked,
    lookers,
    look: looks,
  } = useRadioAsks(
    "radio_scope",
    send,
    connection,
    visible,
    () => radios.value,
    (radio, seconds) => parts.keep?.(radio, seconds * 1000),
  );

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
    look: (looking, radio = first, reach) =>
      looks(looking, radio, reach && (() => (reach() > 0 ? askSeconds(reach()) : undefined))),
  };
}
