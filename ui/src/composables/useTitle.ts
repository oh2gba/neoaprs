// The title of the browser tab follows the number of messages not seen: "(2) NeoAPRS", plain "NeoAPRS" with none (lib/unread.ts); while the tab is alerting (useTabAlert) its words take the title on the beats that show them.
import { watchEffect, type Ref } from "vue";
import { titleText } from "@/lib/unread";

export function useTitle(unread: Ref<number>, alert?: Ref<string | null>): void {
  watchEffect(() => {
    document.title = alert?.value ?? titleText(unread.value);
  });
}
