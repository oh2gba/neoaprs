// The radios of the station for a pane (lib/radios.ts): every radio, those that are on, whether there are several, the main and the email radio, whether a radio is named, the radio a station or a message goes
// on, and the radio this page has just added. Read from the page's context (the topic `radios`, the settings, the status); a pane mounted without the page's context (a test of its own) has no radio. The radios are made once for each page and shared by every pane that asks, and a radio stays the same object while nothing of its own changes, so that a stats-only patch of
// the topic draws again only what shows the counts.
import { computed, effectScope, inject, ref, watch, type ComputedRef, type Ref } from "vue";
import { DAEMON_KEY, type DaemonContext } from "@/composables/useDaemonContext";
import {
  emailRadio,
  enabledRadios,
  isNamed,
  mainRadio,
  messageRadio,
  pageRadios,
  sameRadio,
  senders,
  sendingRadio,
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
  /** the main radio; null while no radio is on */
  main: ComputedRef<PageRadio | null>;
  /** the email radio, which the internet gateways hear; null while there is none */
  email: ComputedRef<PageRadio | null>;
  /** some radio that is on may carry a path */
  allowsPath: ComputedRef<boolean>;
  /** the radio this page added last (the answer `radio_added`), once its row is in the topic; null before */
  added: ComputedRef<PageRadio | null>;
  /** the radio of that id, removed or not; undefined for none */
  byId: (id: RadioId) => PageRadio | undefined;
  /** whether something that came or goes by that radio says its name: where several radios are on, and always for a radio that is not on */
  named: (id: RadioId) => boolean;
  /** the radio a message to the station goes on, as the daemon says it (lib/radios.ts `sendingRadio`; `thread` the conversation's messages; `row` null for a call the book does not hold: the main radio); null for none */
  forStation: (
    row: Partial<Pick<StationRow, "radio_choice" | "radio_now">> | null,
    thread?: readonly Pick<MessageRow, "state" | "radio_now">[],
  ) => PageRadio | null;
  /** the radio of a message: the one its next attempt goes on while it is on its way, else the one it came or went on; null for none */
  forMessage: (row: Pick<MessageRow, "radio_now" | "radio_id">) => PageRadio | null;
  /** a choice of one radio beside a button that asks (Local info, Ask around: plan rule 3.6), made for the pane that calls it */
  choose: () => RadioChoice;
}

/** The radio chosen beside a button: `picked` the operator's (null: the main radio), `radio` the one it goes on (the one picked while it is on, else the main radio), `choices` the radios on that can send, the main radio first. A
 * choice that goes off is forgotten, and does not come back by itself when that radio is on again. */
interface RadioChoice {
  picked: Ref<RadioId | null>;
  radio: ComputedRef<RadioId | null>;
  choices: ComputedRef<PageRadio[]>;
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
    return old !== undefined && old.length === made.length && made.every((radio, i) => radio === old[i]) ? old : made;
  });
  const enabled = computed(() => enabledRadios(all.value));
  const sending = computed(() => senders(all.value));
  const main = computed(() => mainRadio(all.value, context?.status.value ?? null));
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
    main,
    email: computed(() => emailRadio(all.value, context?.status.value ?? null)),
    allowsPath: computed(() => enabled.value.some((radio) => radio.carriesPath)),
    added: computed(() => {
      const id = context?.radioAdded.value?.id;
      return id === undefined ? null : (byId(id) ?? null); // (null until the row of the radio made comes with the topic's next patch)
    }),
    byId,
    named: (id) => isNamed(all.value, id),
    forStation: (row, thread = []) => {
      const id = sendingRadio(row, thread, main.value?.id ?? null);
      return id === null ? null : (byId(id) ?? null);
    },
    forMessage: (row) => {
      const id = messageRadio(row);
      return id === null ? null : (byId(id) ?? null);
    },
    choose: () => {
      const picked = ref<RadioId | null>(null);
      watch(sending, (on) => {
        if (picked.value !== null && !on.some((r) => r.id === picked.value)) picked.value = null;
      }); // (in the scope of the pane that asked: it ends with the pane)
      return {
        picked,
        radio: computed(() => (picked.value !== null && sending.value.some((r) => r.id === picked.value) ? picked.value : (main.value?.id ?? null))),
        choices: computed(() => [...sending.value].sort((a, b) => Number(b.id === main.value?.id) - Number(a.id === main.value?.id))),
      };
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
