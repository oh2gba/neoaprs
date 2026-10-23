// Whether the page is visible (document.visibilityState): false in a background browser tab or a minimised window. A message that comes then is not seen (lib/unread.ts).
import { onBeforeUnmount, onMounted, ref } from "vue";

export function useVisible() {
  const visible = ref(document.visibilityState !== "hidden");
  const update = (): void => {
    visible.value = document.visibilityState !== "hidden";
  };
  onMounted(() => {
    update();
    document.addEventListener("visibilitychange", update);
  });
  onBeforeUnmount(() => document.removeEventListener("visibilitychange", update));
  return visible;
}
