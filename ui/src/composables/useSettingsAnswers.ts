// What the daemon tells back about the settings (composables/useSettings.ts): the topic `config`, told again after every save, is the answer to the request in flight and the new value of every field that was not touched; an `error`
// of `set_config` is the answer too, and names the key it refused.
import { watch, type Ref } from "vue";
import type { Toast } from "@/composables/useDaemon";
import type { useSettingsFeedback } from "@/composables/useSettingsFeedback";
import type { Request, useSettingsQueue } from "@/composables/useSettingsQueue";
import { refusalFor } from "@/lib/settinglinks";
import type { ConfigValues } from "@/protocol/protocol";

export function useSettingsAnswers(
  config: Ref<ConfigValues | null>,
  lastError: Ref<Toast | null>,
  draft: Record<string, string>,
  queue: ReturnType<typeof useSettingsQueue>,
  feedback: ReturnType<typeof useSettingsFeedback>,
  refuse: (request: Request, reason: string, key: string) => void,
): void {
  // a value the person has not touched follows the daemon; one being edited, or waiting in the queue, does not (what the request in flight sent is taken the way the daemon writes it)
  watch(
    config,
    (now, before) => {
      if (!now) return;
      const request = queue.release();
      for (const [key, text] of Object.entries(now.values)) {
        const own = request !== null && draft[key] === request.values[key];
        if (!(key in draft) || (!queue.waiting(key) && (draft[key] === before?.values[key] || own))) draft[key] = text;
      }
      if (request) feedback.saved();
      queue.pump();
    },
    { immediate: true },
  );

  watch(lastError, (toast) => {
    const request = queue.inflight.value;
    if (!toast || !request || toast.cmd !== "set_config") return;
    const where = refusalFor(toast, request.keys);
    queue.release();
    refuse(request, where.reason, where.key);
    queue.pump();
  });
}
