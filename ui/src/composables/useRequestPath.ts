// The path and RF only of a request sent to the stations around (Ask around, Local info), typed,
// kept per `key` so the two boxes mounted side by side each have their own, with what is wrong and
// what the command carries. An empty path is the request's default; a path is calls or aliases
// separated by commas, or DIRECT for none, checked as the daemon checks it (lib/calls.ts).
import { computed, type ComputedRef, type Ref, type WritableComputedRef } from "vue";
import { usePersistedFlag, usePersistedText } from "@/composables/usePersisted";
import { t } from "@/i18n";
import { parsePathSetting } from "@/lib/calls";
import { LIMITS } from "@/protocol/lists";

const PATH_TEXT_MAX = LIMITS.path.textMax;

export interface RequestPath {
  path: Ref<string>;
  rfOnly: WritableComputedRef<boolean>;
  problem: ComputedRef<string>;
  sent: ComputedRef<string | null>;
}

/**
 * Why a path cannot go: not comma-separated calls, too long for a frame, or too many hops with
 * RFONLY.
 */
export function requestPathProblem(text: string, rfOnly: boolean): string {
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
