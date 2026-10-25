// Follow me on the map (components/StationMap.vue): offered while the beacon is mobile and the GPS has a fresh fix, switched on by the person and off by them, by a drag of the map, or when the fix is lost or the beacon is no longer
// mobile. `at` is the place the map keeps centred (the fix) while it is on, else null; useMapFollow eases the map to it.
import { computed, ref, watch, type Ref } from "vue";
import { hasFix } from "@/lib/gpsstatus";
import type { GpsState } from "@/protocol/protocol";

export function useFollowMe(gps: Readonly<Ref<GpsState | null>>) {
  const following = ref(false);
  const canFollow = computed(() => gps.value?.mobile === true && hasFix(gps.value));
  watch(canFollow, (can) => {
    if (!can) following.value = false;
  });
  /** The fix to keep the map on, while Follow me is on. */
  function followAt(): { lat: number; lon: number } | null {
    const fix = gps.value;
    return following.value && hasFix(fix) ? { lat: fix.lat, lon: fix.lon } : null;
  }
  return { following, canFollow, followAt, release: () => (following.value = false) };
}
