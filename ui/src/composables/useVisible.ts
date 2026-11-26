// Whether the page is visible (document.visibilityState): false in a background tab or a minimised
// window.
import { onBeforeUnmount, onMounted, ref, type Ref } from "vue";

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

let shared: Ref<boolean> | null = null;

/**
 * Whether the page is visible, outside any component (no hook to attach the listener to): one
 * value for the page's life, kept by one listener.
 */
export function pageVisible(): Ref<boolean> {
  const now = document.visibilityState !== "hidden";
  if (shared === null) {
    const visible = ref(now);
    document.addEventListener("visibilitychange", () => {
      visible.value = document.visibilityState !== "hidden";
    });
    shared = visible;
  }
  shared.value = now;
  return shared;
}
