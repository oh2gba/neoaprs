// The choices of "Alert me when…" for one station while they are made (StationAlertChoices): the three things to watch and the distance, started from the alert the station has (`stored`, null for none: nothing ticked and
// 10 km), and the alert they make, which the daemon takes (`set_station_alert`; all off takes it away). The distance is a whole number of km in the daemon's range and matters only while "comes within" is ticked: with
// it ticked and the distance wrong there is no alert to send. With `follow`, a stored alert that changes (the daemon's answer, another page) is taken in; the same alert told again changes nothing, so that a distance being typed stays.
import { computed, ref, watch } from "vue";
import { ALERT_KM_DEFAULT, ALERT_KM_MAX, ALERT_KM_MIN } from "@/lib/stationalert";
import type { AlertWhen } from "@/protocol/protocol";

const same = (a: AlertWhen | null, b: AlertWhen | null): boolean => a?.on_air === b?.on_air && a?.within_km === b?.within_km && a?.direct === b?.direct;

export function useAlertDraft(stored: () => AlertWhen | null, follow = false) {
  const onAir = ref(false);
  const near = ref(false);
  const km = ref<number | string>(ALERT_KM_DEFAULT);
  const direct = ref(false);

  function take(alert: AlertWhen | null): void {
    onAir.value = alert?.on_air ?? false;
    near.value = alert?.within_km != null;
    km.value = alert?.within_km ?? ALERT_KM_DEFAULT;
    direct.value = alert?.direct ?? false;
  }
  take(stored());
  if (follow) watch(stored, (now, before) => same(now, before) || take(now));

  const kmOk = computed(() => typeof km.value === "number" && Number.isInteger(km.value) && km.value >= ALERT_KM_MIN && km.value <= ALERT_KM_MAX);

  /** The alert the choices make; null while "comes within" is ticked with a distance the daemon would refuse. */
  function alert(): AlertWhen | null {
    if (near.value && !kmOk.value) return null;
    return { on_air: onAir.value, within_km: near.value && typeof km.value === "number" ? km.value : null, direct: direct.value };
  }

  return { onAir, near, km, direct, kmOk, alert };
}
