// The path and RF only of a request we send to the stations around (the fold under Ask: RequestPath.vue), in Ask around (a general query) and in Local info (a request to QRU): what is typed, remembered by the browser for each of
// the two apart (`key`: the two boxes stay mounted side by side, and each keeps its own), what is wrong with it, and what the command carries. An empty path is the request's own default (the beacon's path for a general query, the
// path of messages to QRU for local info); a path is calls or aliases separated by commas (OH2RDK-7,OH2RCH-2 for a station that a fill-in digipeater relays only when it is named; WIDE1-1,WIDE2-1) or DIRECT for none, checked as the
// daemon checks it (lib/calls.ts).
import { computed, type ComputedRef, type Ref, type WritableComputedRef } from "vue";
import { usePersistedFlag, usePersistedText } from "@/composables/usePersisted";
import { t } from "@/i18n";
import { parsePathSetting } from "@/lib/calls";
import { LIMITS } from "@/protocol/lists";

/** The longest path the field keeps (the daemon takes 256 characters). */
const PATH_TEXT_MAX = 256;

export interface RequestPath {
  path: Ref<string>;
  rfOnly: WritableComputedRef<boolean>;
  /** what is wrong with the path, as the title of the field and of Ask says it; "" when nothing is */
  problem: ComputedRef<string>;
  /** the path the command carries: null for none typed (the request's default) */
  sent: ComputedRef<string | null>;
}

/** Why a path typed for a request cannot go: not calls separated by commas (or more than a frame carries), or so many that RFONLY after them makes too many; "" when it can. */
function requestPathProblem(text: string, rfOnly: boolean): string {
  const setting = parsePathSetting(text);
  if (setting === null) return t("route.calls_hint", { max: LIMITS.path.maxCalls });
  if (rfOnly && setting.kind === "calls" && setting.calls.length >= LIMITS.path.maxCalls) {
    return t("error.path.too_long_rf_only", { count: setting.calls.length, max: LIMITS.path.maxCalls });
  }
  return "";
}

export function useRequestPath(key: string): RequestPath {
  const path = usePersistedText(`${key}.path`, "", PATH_TEXT_MAX);
  const rfOnly = usePersistedFlag(`${key}.rfonly`, ["on", "off"], true);
  return {
    path,
    rfOnly,
    problem: computed(() => requestPathProblem(path.value, rfOnly.value)),
    sent: computed(() => (path.value.trim() === "" ? null : path.value.trim())),
  };
}
