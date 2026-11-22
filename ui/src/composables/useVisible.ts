// Whether the page is visible (document.visibilityState): false in a background tab or a minimised
// window.
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

/** Whether the page is visible, outside any component (no hook to attach the listener to). */
export function pageVisible() {
  const visible = ref(document.visibilityState !== "hidden");
  document.addEventListener("visibilitychange", () => {
    visible.value = document.visibilityState !== "hidden";
  });
  return visible;
}
