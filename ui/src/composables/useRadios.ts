// The radios of the station for a pane (lib/radios.ts): every radio, those that are on, whether there are several, the email radio and the radio of a call no radio heard, whether a radio is named,
// the radio a station or a message goes on, and the radio this page has just added. Read from the page's context (the topic `radios`, the settings, the status); a pane mounted without the page's context (a test of its own) has no radio. The radios are made once for each page and shared by every pane that asks, and a radio stays the same object while nothing of its own changes, so that a stats-only patch of
// the topic draws again only what shows the counts.
import { computed, effectScope, inject, type ComputedRef } from "vue";
import { DAEMON_KEY, type DaemonContext } from "@/composables/useDaemonContext";
import { keepList } from "@/lib/keeplist";
import {
  emailRadio,
  enabledRadios,
  isNamed,
  radioPath,
  sharedPath,
  messageRadio,
  pageRadios,
  sameRadio,
  senders,
  sendingRadio,
  unheardRadio,
  type PageRadio,
  type RadioId,
} from "@/lib/radios";
import type { MessageRow, RadioRow, StationRow } from "@/protocol/protocol";

export interface Radios {
  /** the daemon has told the topic `radios` (until then there is no radio) */
  told: ComputedRef<boolean>;
  /** every radio, removed ones too, in the order of their boxes */
  all: ComputedRef<PageRadio[]>;
  /** the radios that are on */
  enabled: ComputedRef<PageRadio[]>;
  /** more than one radio is on: only then is a radio chosen */
  several: ComputedRef<boolean>;
  /** the radios that are on and can send: the ones a choice of the radio to send on offers (a radio that only listens is in none) */
  senders: ComputedRef<PageRadio[]>;
  /** more than one radio can send: only then is a radio to send on chosen */
  severalSenders: ComputedRef<boolean>;
  /** the radio of a message to a call no radio heard, as the daemon says it (what Route's "Automatic" gives for such a call); null while no radio can send */
  unheard: ComputedRef<PageRadio | null>;
  /** the email radio, as the daemon says it (the one chosen in the Email tab while it is on); null while no radio can send */
  email: ComputedRef<PageRadio | null>;
  /** some radio that is on may carry a path */
  allowsPath: ComputedRef<boolean>;
  /** the path our frames take on the radio, as the daemon gives it (lib/radios.ts `radioPath`): its own, else the path its type recommends, else the station's symbol's; "" for DIRECT */
  pathOf: (radio: PageRadio) => string;
  /** the one path these radios share, of those that may carry one; null while their paths differ, and while none carries one (lib/radios.ts `sharedPath`) */
  sharedPath: (radios: readonly PageRadio[]) => string | null;
  /** the radio this page added last (the answer `radio_added`), once its row is in the topic; null before */
  added: ComputedRef<PageRadio | null>;
  /** the radio of that id, removed or not; undefined for none */
  byId: (id: RadioId) => PageRadio | undefined;
  /** whether something that came or goes by that radio says its name: where several radios are on, and always for a radio that is not on */
  named: (id: RadioId) => boolean;
  /** the radio a message to the station goes on, as the daemon says it (lib/radios.ts `sendingRadio`; `thread` the conversation's messages; `row` null for a call the book does not hold: `unheard`); null for none */
  forStation: (
    row: Partial<Pick<StationRow, "radio_choice" | "radio_now">> | null,
    thread?: readonly Pick<MessageRow, "state" | "radio_now">[],
  ) => PageRadio | null;
  /** the radio of a message: the one its next attempt goes on while it is on its way, else the one it came or went on; null for none */
  forMessage: (row: Pick<MessageRow, "radio_now" | "radio_id">) => PageRadio | null;
}

const NO_RADIOS: ReadonlyMap<string, RadioRow> = new Map();

/** The radios of one page, made in a scope of their own so that they outlive the pane that asked first. */
function make(context: DaemonContext | null): Radios {
  const rows = computed(() => context?.radios.value ?? NO_RADIOS);
  const live = (id: RadioId) => rows.value.get(String(id));
  const all = computed<PageRadio[]>((old) => {
    const made = pageRadios(rows.value, context?.config.value ?? null, live).map((radio) => {
      const was = old?.find((before) => before.id === radio.id);
      return was !== undefined && sameRadio(was, radio) ? was : radio;
    });
    return keepList(old, made);
  });
  const enabled = computed(() => enabledRadios(all.value));
  const sending = computed(() => senders(all.value));
  const unheard = computed(() => unheardRadio(all.value, context?.status.value ?? null));
  const pathOf = (radio: PageRadio): string => radioPath(radio, context?.fallbackPath.value ?? "");
  const ids = new Map<RadioId, ComputedRef<PageRadio | undefined>>();
  const scope = effectScope(true);
  const byId = (id: RadioId): PageRadio | undefined => {
    let found = ids.get(id);
    if (found === undefined) {
      found = scope.run(() => computed(() => all.value.find((radio) => radio.id === id))); // (one for each id, so that a pane that reads one radio is drawn again only when that radio changes)
      if (found === undefined) return all.value.find((radio) => radio.id === id);
      ids.set(id, found);
    }
    return found.value;
  };
  return {
    told: computed(() => (context?.radios.value ?? null) !== null),
    all,
    enabled,
    several: computed(() => enabled.value.length > 1),
    senders: sending,
    severalSenders: computed(() => sending.value.length > 1),
    unheard,
    email: computed(() => emailRadio(all.value, context?.status.value ?? null)),
    allowsPath: computed(() => enabled.value.some((radio) => radio.carriesPath)),
    pathOf,
    sharedPath: (radios) => sharedPath(radios, pathOf),
    added: computed(() => {
      const id = context?.radioAdded.value?.id;
      return id === undefined ? null : (byId(id) ?? null); // (null until the row of the radio made comes with the topic's next patch)
    }),
    byId,
    named: (id) => isNamed(all.value, id),
    forStation: (row, thread = []) => {
      const id = sendingRadio(row, thread, unheard.value?.id ?? null);
      return id === null ? null : (byId(id) ?? null);
    },
    forMessage: (row) => {
      const id = messageRadio(row);
      return id === null ? null : (byId(id) ?? null);
    },
  };
}

const pages = new WeakMap<DaemonContext, Radios>();
let alone: Radios | undefined;

/** Made in a detached scope, so that a pane that unmounts does not stop what the others read. */
function made(context: DaemonContext | null): Radios {
  const radios = effectScope(true).run(() => make(context));
  if (radios === undefined) throw new Error("the radios could not be made");
  return radios;
}

export function useRadios(): Radios {
  const context = inject(DAEMON_KEY, null);
  if (context === null) return (alone ??= made(null));
  let radios = pages.get(context);
  if (radios === undefined) {
    radios = made(context);
    pages.set(context, radios);
  }
  return radios;
}
