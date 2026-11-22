// Follow me on the map: offered while the beacon is mobile and the GPS has a fresh fix; ends when
// switched off, on a drag of the map, or when the fix is lost or the beacon stops being mobile.
// `at` is the fix the map keeps centred while on, else null.
import { computed, ref, watch, type Ref } from "vue";
import { hasFix } from "@/lib/gpsstatus";
import type { GpsState } from "@/protocol/protocol";

export function useFollowMe(gps: Readonly<Ref<GpsState | null>>) {
  const following = ref(false);
  const canFollow = computed(() => gps.value?.mobile === true && hasFix(gps.value));
  watch(canFollow, (can) => {
    if (!can) following.value = false;
  });
  function followAt(): { lat: number; lon: number } | null {
    const fix = gps.value;
    return following.value && hasFix(fix) ? { lat: fix.lat, lon: fix.lon } : null;
  }
  return { following, canFollow, followAt, release: () => (following.value = false) };
}
