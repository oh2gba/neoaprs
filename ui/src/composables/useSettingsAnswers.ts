// What the daemon answers about the settings: `saved` with the number of the request in flight, or
// an `error` of `set_config` that carries it and names the key it refused. The topic `config` is
// never an answer: it is the new value of every field that is not being edited, whoever changed it.
import { watch, type Ref } from "vue";
import type { Toast } from "@/composables/useDaemon";
import type { RadioNames } from "@/i18n/errortext";
import type { useSettingsFeedback } from "@/composables/useSettingsFeedback";
import type { Request, useSettingsQueue } from "@/composables/useSettingsQueue";
import { t } from "@/i18n";
import { refusalFor } from "@/lib/settinglinks";
import { pairFieldOf } from "@/lib/settingspair";
import type { Connection } from "@/lib/hub";
import type { ConfigValues, SavedMessage } from "@/protocol/protocol";

/**
 * Drop keys of a pair the daemon does not send any more (radio removed, type changed); edited
 * or waiting ones stay.
 */
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

/** What the page hears of the daemon besides the settings. */
export interface SettingsLink {
  saved: Ref<SavedMessage | null>;
  connection: Ref<Connection>;
}

export function useSettingsAnswers(
  config: Ref<ConfigValues | null>,
  lastError: Ref<Toast | null>,
  link: SettingsLink,
  draft: Record<string, string>,
  queue: ReturnType<typeof useSettingsQueue>,
  feedback: ReturnType<typeof useSettingsFeedback>,
  refuse: (request: Request, reason: string, key: string) => void,
  radios?: RadioNames,
): void {
  // The request that was just saved: the settings the daemon tells next may carry its keys written
  // the daemon's way (`oh2gba` as `OH2GBA`).
  let landed: Request | null = null;
  // An untouched value follows the daemon; one being edited or queued keeps what was typed, unless
  // the daemon's value of the key I saved changed, which is what my save made of it.
  watch(
    config,
    (now, before) => {
      if (!now) return;
      const request = queue.inflight.value ?? landed;
      landed = null;
      const moved = (key: string): boolean => (now.values[key] ?? "") !== (before?.values[key] ?? "");
      for (const [key, text] of Object.entries(now.values)) {
        const own = request !== null && draft[key] === request.values[key] && moved(key);
        if (!(key in draft) || (!queue.waiting(key) && (draft[key] === before?.values[key] || own))) draft[key] = text;
      }
      dropGonePairs(draft, now.values, before?.values, queue, request);
    },
    { immediate: true },
  );

  watch(link.saved, (message) => {
    if (!message) return;
    const request = queue.settle(message.id);
    if (request === null) return;
    landed = request;
    feedback.saved();
    queue.pump();
  });

  watch(lastError, (toast) => {
    if (!toast || toast.cmd !== "set_config") return;
    const request = queue.settle(toast.id);
    if (request === null) return;
    const where = refusalFor(toast, request.keys, radios);
    refuse(request, where.reason, where.key);
    queue.pump();
  });

  // The daemon forgets a request whose socket closed: refuse what was out, keeping what was typed.
  watch(link.connection, (state) => state !== "open" && queue.giveUp(t("settings.not_sent")));
}
