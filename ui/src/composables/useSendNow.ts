// The two "send now" buttons of the My station tab (Beacon now, Send status now). A button asks
// twice, because what goes on the air cannot be taken back; only one is armed at a time. Both are
// disabled while the TNC is not connected or a settings save runs. The first press is forgotten
// after a few seconds, when the TNC drops, when the save starts or when a place is picked on the
// map.
import { computed, watch, type Ref } from "vue";
import { t } from "@/i18n";
import { useSure } from "@/composables/useSure";

export type SendKey = "beacon" | "status";

export function useSendNow(connected: Ref<boolean>, saving: Ref<boolean>, picking: Ref<boolean>, endPick: () => void) {
  const sure = useSure<SendKey>();
  const ready = computed(() => connected.value && !saving.value);
  const why = computed(() => (saving.value ? t("settings.saving") : undefined));

  watch(ready, (now) => {
    if (!now) sure.disarm();
  });
  watch(picking, (now) => {
    if (now) sure.disarm();
  });

  function press(key: SendKey, act: () => void): void {
    if (sure.armed.value !== key && picking.value) endPick();
    sure.press(key, act);
  }

  return { armed: sure.armed, ready, why, press };
}
