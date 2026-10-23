// Calls `changed` when the element changes size (the map, which a phone hides under the open tab and shows again, or whose panel is dragged: MapLibre has to be told, it only listens to the window). Without a ResizeObserver (a very old browser) the
// window's own resize event is all there is.
import { onBeforeUnmount, onMounted, type Ref } from "vue";

export function useResized(el: Readonly<Ref<Element | null>>, changed: () => void): void {
  let observer: ResizeObserver | null = null;
  onMounted(() => {
    if (el.value && typeof ResizeObserver === "function") {
      observer = new ResizeObserver(() => changed());
      observer.observe(el.value);
    }
  });
  onBeforeUnmount(() => {
    observer?.disconnect();
    observer = null;
  });
}
