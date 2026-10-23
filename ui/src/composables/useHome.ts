// Where our own station is: the place of the settings, else the one the daemon's status has; null while there is none.
import { computed, type Ref } from "vue";
import type { Home } from "@/lib/mapview";
import type { ConfigValues, StatusMessage } from "@/protocol/protocol";

export function useHome(config: Readonly<Ref<ConfigValues | null>>, status: Readonly<Ref<StatusMessage | null>>) {
  return computed<Home | null>(() => {
    const place = (text: string | number | null | undefined): number => (text === undefined || text === null || text === "" ? NaN : Number(text));
    const lat = place(config.value?.values["station/lat"] ?? status.value?.lat);
    const lon = place(config.value?.values["station/lon"] ?? status.value?.lon);
    return Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null;
  });
}
