// How wide an element is, kept up to date with a ResizeObserver: the page decides by the width of the panel it is in, not by the window, since the panel beside the map can be narrow on a wide screen.
// It is 0 until the element is mounted, and a width of 0 (the element is hidden, as the tab of a panel not on show is) is not taken: the last real width stays.
import { onBeforeUnmount, onMounted, ref, type Ref } from "vue";

export function useElementWidth(element: Ref<HTMLElement | null>) {
  const width = ref(0);
  let observer: ResizeObserver | undefined;

  onMounted(() => {
    const node = element.value;
    if (node === null) return;
    width.value = node.clientWidth;
    if (typeof ResizeObserver === "undefined") return;
    observer = new ResizeObserver((entries) => {
      const next = entries[0]?.contentRect.width ?? 0;
      if (next > 0) width.value = next;
    });
    observer.observe(node);
  });
  onBeforeUnmount(() => observer?.disconnect());

  return width;
}
