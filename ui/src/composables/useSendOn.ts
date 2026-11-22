// Send on, one pattern for everything that goes to no station in particular: the beacon and the
// status, Ask around and Local info, bound to the radios' settings; and `useDraftSendOn`, the same
// row bound to a draft that the thing's Save or Post applies. A tick for each radio that is on and
// can send, while several are, is applied at once. A tick sent waits for the daemon like a draft
// and shows the value in force otherwise; none is ticked while the radios it was ticked for are
// off (lib/beaconstatus.ts `sendOnTicks`). The daemon's refusal of a tick is the row's one line,
// which the next press takes away.
import { computed, type ComputedRef } from "vue";
import { draftTicks, inForce, ticked } from "@/lib/sendon";
import { useDaemonContext } from "@/composables/useDaemonContext";
import type { Radios } from "@/composables/useRadios";
import { radioValueOf, sendOnTicks, type SendOnField, type SendOnTick } from "@/lib/beaconstatus";
import type { PageRadio, RadioId } from "@/lib/radios";

export interface SendOn {
  ticks: ComputedRef<SendOnTick[]>;
  radios: ComputedRef<PageRadio[]>;
  error: ComputedRef<string>;
  tick: (key: string, on: boolean) => void;
}

const text = (on: boolean): string => (on ? "true" : "false");

export function useSendOn(field: SendOnField, radios: Pick<Radios, "severalSenders" | "senders">): SendOn {
  const { config, settings } = useDaemonContext();
  function ticked(key: string, radio: PageRadio): boolean {
    const draft = settings.draft[key];
    return (draft === "true" || draft === "false" ? draft : (radioValueOf(config.value, key) ?? String(radio.row.choices[field]))) === "true";
  }
  const ticks = computed<SendOnTick[]>(() => (radios.severalSenders.value ? sendOnTicks(radios.senders.value, ticked, field) : []));
  const on = computed(() =>
    ticks.value.length === 0 ? [...radios.senders.value] : radios.senders.value.filter((radio) => ticks.value.some((tick) => tick.id === radio.id && tick.on)),
  );
  const error = computed(() => ticks.value.map((tick) => settings.errors[tick.key] ?? "").find((reason) => reason !== "") ?? "");
  function tick(key: string, to: boolean): void {
    for (const one of ticks.value) delete settings.errors[one.key];
    settings.change({ [key]: text(to) });
  }
  return { ticks, radios: on, error, tick };
}

export interface DraftSendOn {
  ticks: ComputedRef<SendOnTick[]>;
  radios: ComputedRef<PageRadio[]>;
  tick: (key: string, on: boolean) => void;
}

/**
 * Send on bound to a draft, applied by the form's own Save or Post: `own` is the draft's set, `set`
 * takes the set after a tick.
 */
export function useDraftSendOn(
  own: () => readonly RadioId[],
  set: (ids: RadioId[]) => void,
  name: string,
  radios: Pick<Radios, "severalSenders" | "senders">,
): DraftSendOn {
  const ids = computed(() => radios.senders.value.map((radio) => radio.id));
  const ticks = computed<SendOnTick[]>(() => (radios.severalSenders.value ? draftTicks(radios.senders.value, own(), name) : []));
  const on = computed(() => {
    const shown = inForce(own(), ids.value);
    return radios.senders.value.filter((radio) => shown.includes(radio.id));
  });
  function tick(key: string): void {
    const pressed = ticks.value.find((one) => one.key === key);
    if (pressed !== undefined) set(ticked(own(), ids.value, pressed.id));
  }
  return { ticks, radios: on, tick };
}
