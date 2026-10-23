// The two "send now" buttons of the Beacon tab (Beacon now in the Beacon group, Send status now in the Status group). A button asks twice (what goes on the air cannot be taken back: the first press says "Really send?"), only one is armed at a time,
// both are disabled while the TNC is not connected or while a change of the settings is being saved (what is sent is what is in force), and the first press is forgotten after a few seconds, when the TNC drops or the save starts, and when a place is
// picked on the map (picking a place and a send that waits for its second press do not go together: starting one ends the other).
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

  /** The first press arms the button (and ends a pick of a place); the second sends. */
  function press(key: SendKey, act: () => void): void {
    if (sure.armed.value !== key && picking.value) endPick();
    sure.press(key, act);
  }

  return { armed: sure.armed, ready, why, press };
}
