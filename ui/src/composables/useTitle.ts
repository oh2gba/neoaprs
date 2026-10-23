// The title of the browser tab follows the number of messages not seen: "(2) NeoAPRS", plain "NeoAPRS" with none (lib/unread.ts).
import { watchEffect, type Ref } from "vue";
import { titleText } from "@/lib/unread";

export function useTitle(unread: Ref<number>): void {
  watchEffect(() => {
    document.title = titleText(unread.value);
  });
}
