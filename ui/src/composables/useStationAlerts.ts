// An alert set on a station fired (the daemon's message `station_alert`, which every page that is open is told once): the page alerts as it does for a message to us, as the choice of this browser says (the chime, the pop-up, the browser
// tab; composables/useBrowserAlerts.ts), and says what happened in its toast with the time ("12:03 OH2XYZ is on the air"), whatever that choice is. Each message is taken as it comes (`sync`): one packet can fire two alerts at once.
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
