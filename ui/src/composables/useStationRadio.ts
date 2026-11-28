// The radio the messages to a station go on, as the Messages, Email and Stations tabs show it and
// Route chooses it. It is the daemon's (lib/radios.ts `sendingRadio`). It is named only where
// more than one radio is on, and always while it is not on. A control that sends over it is off
// while its link is down. Route holds, in order: the radio choice (the radios that are on and
// send, and "Automatic"), where more than one sends (greyed on the email radio for the email
// gateway); then the station's own path on the radio in force and RF only, while a radio that is
// on may carry a path. A path belongs to the radio it was set on: radio 1's is the topic
// `station_prefs`, another radio's the station row's `paths`. For a call the book does not hold,
// the topic `call_routes` says the choice, the radio now and the paths as a row would.
import { computed } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { t } from "@/i18n";
import { normalizeCall } from "@/lib/calls";
import { radioBlockedReason } from "@/lib/compose";
import { isGateway } from "@/lib/messages";
import type { PageRadio, RadioId } from "@/lib/radios";
import type { CallRoute, MessageRow, StationRow } from "@/protocol/protocol";

/**
 * The radio whose path for a station the topic `station_prefs` carries; the target of a path
 * command naming no radio.
 */
export const PREFS_RADIO: RadioId = 1;

/**
 * The radio an incoming message came on, where radios are named; null for none or for one of ours.
 */
export function useCameOn(): (m: Pick<MessageRow, "direction" | "radio_id">) => PageRadio | null {
  const radios = useRadios();
  return (m) =>
    m.direction === "in" && m.radio_id !== null && radios.named(m.radio_id) ? (radios.byId(m.radio_id) ?? null) : null;
}

/**
 * The radio of the messages to the station `call` and its Route (`thread` gives the messages in
 * flight).
 */
export function useStationRadio(
  call: () => string,
  row: () => StationRow | null,
  thread: () => readonly Pick<MessageRow, "state" | "radio_now">[] = () => [],
) {
  const radios = useRadios();
  const { prefs, fallbackPath, send, callRoutes } = useDaemonContext();
  const gateway = computed(() => isGateway(call()));
  /** The station's row, else the route the daemon keeps for a call it does not hold; null for neither. */
  const route = computed<StationRow | CallRoute | null>(
    () => row() ?? callRoutes.value.get(normalizeCall(call())) ?? null,
  );
  const over = computed(() =>
    gateway.value ? radios.email.value : (radios.forStation(route.value, thread()) ?? radios.unheard.value),
  );
  const named = computed(() => over.value !== null && radios.named(over.value.id));
  const onPrefs = computed(() => over.value === null || over.value.id === PREFS_RADIO);
  const paths = computed<ReadonlyMap<string, string>>(() => {
    if (onPrefs.value) return prefs.paths.value;
    const own = route.value?.paths[String(over.value?.id)];
    return new Map(own === undefined ? [] : [[normalizeCall(call()), own]]);
  });
  const fallback = computed(() => (over.value === null ? fallbackPath.value : radios.pathOf(over.value)));
  // A radio that only listens is no radio for messages.
  const choices = computed<readonly PageRadio[]>(() => (radios.severalSenders.value ? radios.senders.value : []));
  const pathShown = computed(() => radios.allowsPath.value);
  const radioOf = (): RadioId | undefined => (onPrefs.value ? undefined : over.value?.id);
  return {
    over,
    named,
    offline: computed(() => radioBlockedReason(over.value, named.value)),
    choices,
    /** The radio cannot be chosen here (the email gateway); Route's row stays, greyed. */
    fixed: gateway,
    choice: computed(() => (gateway.value ? (radios.email.value?.id ?? null) : (route.value?.radio_choice ?? null))),
    auto: computed(() => (!gateway.value && route.value?.radio_choice == null ? (over.value?.name ?? null) : null)),
    /** The bytes of text a message holds on the radio now where its frame leaves fewer; null: the message's own. */
    textMax: computed(() => route.value?.text_max ?? null),
    pathShown,
    pathless: computed(() =>
      pathShown.value && over.value !== null && !over.value.carriesPath
        ? t("radio.no_path", { name: over.value.name })
        : undefined,
    ),
    reply: computed(() =>
      over.value === null || over.value.carriesPath ? "" : (row()?.replies[String(over.value.id)] ?? ""),
    ),
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
