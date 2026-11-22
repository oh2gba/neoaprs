// The browser tab title follows the unseen messages count: "(2) NeoAPRS", else "NeoAPRS"; an
// alerting tab (useTabAlert) shows its words on the beats.
import { watchEffect, type Ref } from "vue";
import { titleText } from "@/lib/unread";

export function useTitle(unread: Ref<number>, alert?: Ref<string | null>): void {
  watchEffect(() => {
    document.title = alert?.value ?? titleText(unread.value);
  });
}
