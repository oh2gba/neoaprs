// What the daemon tells back about the settings (composables/useSettings.ts): the topic `config`, told again after every save, is the answer to the request in flight and the new value of every field that was not touched; an `error`
// of `set_config` is the answer too, and names the key it refused.
import { watch, type Ref } from "vue";
import type { Toast } from "@/composables/useDaemon";
import type { RadioNames } from "@/i18n/errortext";
import type { useSettingsFeedback } from "@/composables/useSettingsFeedback";
import type { Request, useSettingsQueue } from "@/composables/useSettingsQueue";
import { refusalFor } from "@/lib/settinglinks";
import { pairFieldOf } from "@/lib/settingspair";
import type { ConfigValues } from "@/protocol/protocol";

/** A pair's keys the daemon no longer tells (a radio removed, a type changed) leave the draft, so that the free calls do not count a pair that is gone; one edited or waiting for its answer stays. */
function dropGonePairs(
  draft: Record<string, string>,
  told: Readonly<Record<string, string>>,
  before: Readonly<Record<string, string>> | undefined,
  queue: ReturnType<typeof useSettingsQueue>,
  request: Request | null,
): void {
  for (const key of Object.keys(draft)) {
    const kept = key in told || queue.waiting(key) || request?.keys.includes(key) || draft[key] !== before?.[key];
    if (pairFieldOf(key) !== null && !kept) delete draft[key];
  }
}

export function useSettingsAnswers(
  config: Ref<ConfigValues | null>,
  lastError: Ref<Toast | null>,
  draft: Record<string, string>,
  queue: ReturnType<typeof useSettingsQueue>,
  feedback: ReturnType<typeof useSettingsFeedback>,
  refuse: (request: Request, reason: string, key: string) => void,
  radios?: RadioNames,
): void {
  // The answer carries no id, so a tell of the settings for another reason releases the request in flight too. A tell that changed none of its keys may be such a one: the request is kept as `unsure`, so that a
  // refusal of it that comes later, while the next one is out, still reaches its field.
  let unsure: Request | null = null;
  // a value the person has not touched follows the daemon; one being edited, or waiting in the queue, does not (what the request in flight sent is taken the way the daemon writes it)
  watch(
    config,
    (now, before) => {
      if (!now) return;
      const request = queue.release();
      const changed = (r: Request): boolean => r.keys.some((key) => (now.values[key] ?? "") !== (before?.values[key] ?? ""));
      if (request !== null) unsure = changed(request) ? null : request;
      else if (unsure !== null && changed(unsure)) unsure = null;
      for (const [key, text] of Object.entries(now.values)) {
        const own = request !== null && draft[key] === request.values[key];
        if (!(key in draft) || (!queue.waiting(key) && (draft[key] === before?.values[key] || own))) draft[key] = text;
      }
      dropGonePairs(draft, now.values, before?.values, queue, request);
      if (request) feedback.saved();
      queue.pump();
    },
    { immediate: true },
  );

  watch(lastError, (toast) => {
    if (!toast || toast.cmd !== "set_config") return;
    const request = queue.inflight.value;
    const earlier = unsure;
    // a refusal that names a key of that request and none of the one in flight is its own: it goes to its field, and the one in flight still waits
    if (earlier !== null && toast.key !== null && earlier.keys.includes(toast.key) && !request?.keys.includes(toast.key)) {
      unsure = null;
      refuse(earlier, refusalFor(toast, earlier.keys, radios).reason, toast.key);
      return;
    }
    if (!request) return;
    const where = refusalFor(toast, request.keys, radios);
    queue.release();
    refuse(request, where.reason, where.key);
    queue.pump();
  });
}
