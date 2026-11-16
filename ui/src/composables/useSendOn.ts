// Send on of the My station tab (components/SendOn.vue), one pattern for the beacon and the status: a tick for each radio that is on and can send, while several are (the radios' own `radio/<id>/beacon`, or
// `radio/<id>/status`), applied at once. A tick sent waits for the daemon as its draft and shows the value in force else; while none is ticked the main radio's is, ticked and greyed, for the thing goes out on it
// (lib/beaconstatus.ts `sendOnTicks`), and a tick of another radio keeps that one ticked, as it was seen. The daemon's refusal of a tick is the row's one line, which the next press takes away.
import { computed, type ComputedRef } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import type { Radios } from "@/composables/useRadios";
import { radioValueOf, sendOnTicks, type SendOnField, type SendOnTick } from "@/lib/beaconstatus";
import type { PageRadio } from "@/lib/radios";

export interface SendOn {
  /** the ticks, none while one radio that can send is on (the tab is as it was) */
  ticks: ComputedRef<SendOnTick[]>;
  /** the daemon's refusal of the latest tick, "" for none */
  error: ComputedRef<string>;
  /** a tick pressed: the radio's setting to `on` */
  tick: (key: string, on: boolean) => void;
}

export function useSendOn(field: SendOnField, radios: Pick<Radios, "severalSenders" | "senders" | "main">): SendOn {
  const { config, settings } = useDaemonContext();
  function ticked(key: string, radio: PageRadio): boolean {
    const draft = settings.draft[key];
    const text = draft === "true" || draft === "false" ? draft : (radioValueOf(config.value, key) ?? String(radio.row.choices[field]));
    return text === "true";
  }
  const ticks = computed<SendOnTick[]>(() => (radios.severalSenders.value ? sendOnTicks(radios.senders.value, ticked, radios.main.value, field) : []));
  const error = computed(() => ticks.value.map((tick) => settings.errors[tick.key] ?? "").find((text) => text !== "") ?? "");
  function tick(key: string, on: boolean): void {
    for (const one of ticks.value) delete settings.errors[one.key];
    const held = ticks.value.filter((one) => one.held && one.key !== key).map((one): [string, string] => [one.key, "true"]);
    settings.change({ ...Object.fromEntries(held), [key]: on ? "true" : "false" });
  }
  return { ticks, error, tick };
}
