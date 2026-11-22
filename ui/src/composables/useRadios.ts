// The radios of the station for a pane (lib/radios.ts): every radio, those that are on, the email
// radio, the radio a station or message goes on, and the radio this page just added. Read from
// the page's context; a pane mounted without one has no radio. The radios are made once per page
// and shared, and a radio stays the same object while nothing of its own changes, so a
// stats-only patch redraws only what shows the counts.
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
  told: ComputedRef<boolean>;
  all: ComputedRef<PageRadio[]>;
  enabled: ComputedRef<PageRadio[]>;
  several: ComputedRef<boolean>;
  senders: ComputedRef<PageRadio[]>;
  severalSenders: ComputedRef<boolean>;
  unheard: ComputedRef<PageRadio | null>;
  email: ComputedRef<PageRadio | null>;
  allowsPath: ComputedRef<boolean>;
  pathOf: (radio: PageRadio) => string;
  sharedPath: (radios: readonly PageRadio[]) => string | null;
  added: ComputedRef<PageRadio | null>;
  byId: (id: RadioId) => PageRadio | undefined;
  named: (id: RadioId) => boolean;
  forStation: (
    row: Partial<Pick<StationRow, "radio_choice" | "radio_now">> | null,
    thread?: readonly Pick<MessageRow, "state" | "radio_now">[],
  ) => PageRadio | null;
  forMessage: (row: Pick<MessageRow, "radio_now" | "radio_id">) => PageRadio | null;
}

const NO_RADIOS: ReadonlyMap<string, RadioRow> = new Map();

/**
 * The radios of one page, made in their own scope so that they outlive the pane that asked first.
 */
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
      found = scope.run(() => computed(() => all.value.find((radio) => radio.id === id)));
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
      return id === undefined ? null : (byId(id) ?? null);
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
