// What the page works out from the stations heard: ours with the symbol of the settings (the daemon has heard none of its own), the path the daemon suggests for each station that has one, and the stations heard direct.
import { computed, type Ref } from "vue";
import { withOwnSymbol } from "@/lib/stations";
import type { ConfigValues, StationRow } from "@/protocol/protocol";

export function useHeardIndex(heard: ReadonlyMap<string, StationRow>, config: Readonly<Ref<ConfigValues | null>>) {
  const stations = computed(() => withOwnSymbol(heard, config.value?.values));
  const suggestions = computed(() => new Map([...stations.value].map(([call, row]) => [call, row.suggested_path] as const)));
  const heardDirect = computed(() => new Set([...stations.value].filter(([, row]) => row.heard_direct > 0).map(([call]) => call)));
  return { stations, suggestions, heardDirect };
}
