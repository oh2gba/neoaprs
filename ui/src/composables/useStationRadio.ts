// The radio the messages to a station go on, as the Messages, Email and Stations tabs show it, and Route, where it is chosen (plan sections 6 and 6a). The radio is the daemon's (lib/radios.ts `sendingRadio`: the operator's
// choice in force, a message of ours on its way, the station's radio now; for a call the book does not hold and for a row that names none the radio of a call no radio heard, which the daemon names). It is named only where more
// than one radio is on, and always while it is not on. A control that sends over it is off while its link is down, with that as its reason. Route holds, in this order: the radio (the radios that are on and send, and "Automatic",
// which names the radio it gives), where more than one sends (greyed on "Automatic" for a call the book does not hold: the daemon keeps a choice by call, but only the station's row says it back; the row is there so that nothing
// moves when the station is heard; greyed on the email radio for the email gateway, whose radio is chosen in the Email tab and nowhere else); then the station's own path on the radio in force and RF only, while a radio that is on may carry a path, greyed with the value kept
// while the radio in force carries none. A path belongs to the radio it was set on: radio 1's is the topic `station_prefs`, as before, and another radio's the station row's `paths`, set and cleared with the radio named.
import { computed } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { t } from "@/i18n";
import { normalizeCall } from "@/lib/calls";
import { radioBlockedReason } from "@/lib/compose";
import { isGateway } from "@/lib/messages";
import type { PageRadio, RadioId } from "@/lib/radios";
import type { MessageRow, StationRow } from "@/protocol/protocol";

/** The radio whose path for a station the topic `station_prefs` carries, and which a path command that names no radio is for. */
export const PREFS_RADIO: RadioId = 1;

/** The radio a message that came in came on, where radios are named (more than one on, or that radio not on); null for none, and for one of ours (its chain says it). A bubble and a mail row show it the same way. */
export function useCameOn(): (m: Pick<MessageRow, "direction" | "radio_id">) => PageRadio | null {
  const radios = useRadios();
  return (m) => (m.direction === "in" && m.radio_id !== null && radios.named(m.radio_id) ? (radios.byId(m.radio_id) ?? null) : null);
}

/** The radio of the messages to the station `call` (its row, null for a call the book does not hold; `thread`, the conversation's messages, for one on its way) and its Route. */
export function useStationRadio(call: () => string, row: () => StationRow | null, thread: () => readonly Pick<MessageRow, "state" | "radio_now">[] = () => []) {
  const radios = useRadios();
  const { prefs, fallbackPath, send } = useDaemonContext();
  /** the station is the email gateway: its radio is the email radio, which the Email tab chooses */
  const gateway = computed(() => isGateway(call()));
  const over = computed(() => (gateway.value ? radios.email.value : (radios.forStation(row(), thread()) ?? radios.unheard.value)));
  const named = computed(() => over.value !== null && radios.named(over.value.id));
  /** the radio's path is the topic `station_prefs` (radio 1, and while there is no radio) */
  const onPrefs = computed(() => over.value === null || over.value.id === PREFS_RADIO);
  const paths = computed<ReadonlyMap<string, string>>(() => {
    if (onPrefs.value) return prefs.paths.value;
    const own = row()?.paths[String(over.value?.id)];
    return new Map(own === undefined ? [] : [[normalizeCall(call()), own]]);
  });
  /** the path of the radio in force where the station has none of its own, as the daemon gives it (its own setting, else the path its type recommends, else the station's symbol's); with no radio the symbol's */
  const fallback = computed(() => (over.value === null ? fallbackPath.value : radios.pathOf(over.value)));
  const choices = computed<readonly PageRadio[]>(() => (radios.severalSenders.value ? radios.senders.value : [])); // (a radio that only listens is no radio for messages)
  const pathShown = computed(() => radios.allowsPath.value);
  const radioOf = (): RadioId | undefined => (onPrefs.value ? undefined : over.value?.id);
  return {
    over,
    named,
    /** why a control that sends over the radio is off; undefined while its link is up */
    offline: computed(() => radioBlockedReason(over.value, named.value)),
    /** the radios Route's first row offers: those that send, where more than one does */
    choices,
    /** the radio cannot be chosen here: a call the book does not hold (the daemon keeps a choice by call, but only the station's row says it back), and the email gateway (the Email tab chooses its radio: a choice is
     * offered once); Route's row is there all the same, greyed */
    fixed: computed(() => row() === null || gateway.value),
    /** the radio the operator chose for the station; null for the daemon's own choice. For the email gateway the email radio, which the greyed row then names */
    choice: computed(() => (gateway.value ? (radios.email.value?.id ?? null) : (row()?.radio_choice ?? null))),
    /** the radio "Automatic" gives now (none while a choice is in force, which the row says instead) */
    auto: computed(() => (!gateway.value && row()?.radio_choice == null ? (over.value?.name ?? null) : null)),
    /** Path and RF only are in Route: a radio that is on may carry a path */
    pathShown,
    /** why what needs a path is greyed: the radio in force carries none; undefined while it carries one */
    pathless: computed(() => (pathShown.value && over.value !== null && !over.value.carriesPath ? t("radio.no_path", { name: over.value.name }) : undefined)),
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
