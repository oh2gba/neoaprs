// A station alert fired (the daemon's `station_alert`, sent once to every open page): the page
// alerts as for a message to us, as this browser's choice says, and says what happened in its
// toast with the time. Each message is taken as it comes (`sync`): one packet can fire two alerts.
import { watch, type Ref } from "vue";
import type { BrowserAlerts } from "@/composables/useBrowserAlerts";
import { firedLine } from "@/lib/stationalert";
import type { StationAlertMessage } from "@/protocol/protocol";

export function useStationAlerts(
  fired: Readonly<Ref<StationAlertMessage | null>>,
  alerts: Pick<BrowserAlerts, "announceStation">,
  say: (text: string) => void,
): void {
  watch(
    fired,
    (message) => {
      if (message === null) return;
      alerts.announceStation(message);
      say(firedLine(message));
    },
    { flush: "sync" },
  );
}
