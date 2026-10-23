// The size of the window and the size class it makes (lib/layout.ts: phone, tablet, desktop), kept up to date: a window that is resized, a phone that is turned.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { sizeOf } from "@/lib/layout";

export function useViewport() {
  const width = ref(window.innerWidth);
  const height = ref(window.innerHeight);
  const size = computed(() => sizeOf(width.value, height.value));
  const measure = (): void => {
    width.value = window.innerWidth;
    height.value = window.innerHeight;
  };
  onMounted(() => {
    window.addEventListener("resize", measure);
    window.addEventListener("orientationchange", measure);
  });
  onBeforeUnmount(() => {
    window.removeEventListener("resize", measure);
    window.removeEventListener("orientationchange", measure);
  });
  return { width, height, size };
}
