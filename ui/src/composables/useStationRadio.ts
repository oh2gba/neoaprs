// The radio the messages to a station go on, as the Messages, Email and Stations tabs show it, and Route, where it is chosen (plan sections 6 and 6a). The radio is the daemon's (lib/radios.ts `sendingRadio`: the operator's
// choice in force, a message of ours on its way, the station's radio now; the main radio for a call the book does not hold and for a row that names none). It is named only where more than one radio is on, and always while it
// is not on. A control that sends over it is off while its link is down, with that as its reason. Route holds, in this order: the radio (the radios that are on and "Automatic"), where more than one is on and the book holds the
// station (the daemon keeps a choice by call, but only the station's row says it back); then the station's own path on the radio in force and RF only, while a radio that is on may carry a path, greyed with the value kept
// while the radio in force carries none. A path belongs to the radio it was set on: radio 1's is the topic `station_prefs`, as before, and another radio's the station row's `paths`, set and cleared with the radio named.
import { computed } from "vue";
import type { TagTone } from "@/components/TagMark.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { t } from "@/i18n";
import { normalizeCall, pathCalls } from "@/lib/calls";
import { tncNotConnected } from "@/lib/compose";
import type { PageRadio, RadioId } from "@/lib/radios";
import { recommendedPath } from "@/lib/symbols";
import type { MessageRow, StationRow } from "@/protocol/protocol";

/** The radio whose path for a station the topic `station_prefs` carries, and which a path command that names no radio is for. */
const PREFS_RADIO: RadioId = 1;

/** The tone of a radio's tag: dashed for a Dummy radio whatever its kind, the inverse pill for HF, neutral for the rest. */
export const radioTone = (radio: Pick<PageRadio, "kind" | "dummy">): TagTone => (radio.dummy ? "dummy" : radio.kind === "hf" ? "hf" : "neutral");

/** The radio a message that came in came on, where radios are named (more than one on, or that radio not on); null for none, and for one of ours (its chain says it). A bubble and a mail row show it the same way. */
export function useCameOn(): (m: Pick<MessageRow, "direction" | "radio_id">) => PageRadio | null {
  const radios = useRadios();
  return (m) => (m.direction === "in" && m.radio_id !== null && radios.named(m.radio_id) ? (radios.byId(m.radio_id) ?? null) : null);
}

/** Why a control that sends over the radio is off: undefined while its link is up; "HF: not connected" where it is named, else the words of before. */
export function linkReason(radio: PageRadio | null, named: boolean): string | undefined {
  if (radio?.connected === true) return undefined;
  return radio !== null && named ? t("radio.not_connected", { name: radio.name }) : tncNotConnected();
}

/** The radio of the messages to the station `call` (its row, null for a call the book does not hold; `thread`, the conversation's messages, for one on its way) and its Route. */
export function useStationRadio(call: () => string, row: () => StationRow | null, thread: () => readonly Pick<MessageRow, "state" | "radio_now">[] = () => []) {
  const radios = useRadios();
  const { prefs, fallbackPath, config, send } = useDaemonContext();
  const over = computed(() => radios.forStation(row(), thread()) ?? radios.main.value);
  const named = computed(() => over.value !== null && radios.named(over.value.id));
  /** the radio's path is the topic `station_prefs` (radio 1, and while there is no radio) */
  const onPrefs = computed(() => over.value === null || over.value.id === PREFS_RADIO);
  const paths = computed<ReadonlyMap<string, string>>(() => {
    if (onPrefs.value) return prefs.paths.value;
    const own = row()?.paths[String(over.value?.id)];
    return new Map(own === undefined ? [] : [[normalizeCall(call()), own]]);
  });
  /** the path of the radio in force where the station has none of its own: its own setting, radio 1's the beacon's path of before */
  const fallback = computed(() => {
    const text = onPrefs.value ? undefined : over.value?.settings["path"];
    if (text === undefined) return fallbackPath.value;
    const values = config.value?.values ?? {};
    return (pathCalls(text, recommendedPath(values["station/symbol_table"] ?? "", values["station/symbol_code"] ?? "")) ?? [text]).join(",");
  });
  const choices = computed<readonly PageRadio[]>(() => (radios.several.value && row() !== null ? radios.enabled.value : []));
  const pathShown = computed(() => radios.allowsPath.value);
  const radioOf = (): RadioId | undefined => (onPrefs.value ? undefined : over.value?.id);
  return {
    over,
    named,
    /** why a control that sends over the radio is off; undefined while its link is up */
    offline: computed(() => linkReason(over.value, named.value)),
    /** the radios Route's first row offers; none where one radio is on, and for a call the book does not hold */
    choices,
    /** the radio the operator chose for the station; null for the daemon's own choice */
    choice: computed(() => row()?.radio_choice ?? null),
    /** the radio "Automatic" gives now (none while a choice is in force, which the row says instead) */
    auto: computed(() => (row()?.radio_choice == null ? (over.value?.name ?? null) : null)),
    /** Path and RF only are in Route: a radio that is on may carry a path */
    pathShown,
    /** why what needs a path is greyed: the radio in force carries none; undefined while it carries one */
    pathless: computed(() => (pathShown.value && over.value !== null && !over.value.carriesPath ? t("route.no_path", { name: over.value.name }) : undefined)),
    /** Route has a row to show */
    shown: computed(() => pathShown.value || choices.value.length > 0),
    paths,
    fallback,
    setPath: (to: string, path: string): void => {
      const radio = radioOf();
      if (radio === undefined) prefs.setPath(to, path);
      else send({ cmd: "set_station_path", call: to, path, radio });
    },
    clearPath: (to: string): void => {
      const radio = radioOf();
      if (radio === undefined) prefs.clearPath(to);
      else send({ cmd: "clear_station_path", call: to, radio });
    },
    choose: (to: string, radio: RadioId | null): void => void send({ cmd: "station_radio", call: to, radio }),
  };
}
