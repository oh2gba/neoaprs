// Calls `changed` when the element changes size (the map, which a phone hides and shows again or
// whose panel is dragged: MapLibre only listens to the window). Without a ResizeObserver the
// window's resize event is all there is.
import { onBeforeUnmount, watch, type Ref } from "vue";

export function useResized(el: Readonly<Ref<Element | null>>, changed: () => void): void {
  let observer: ResizeObserver | null = null;
  const stop = (): void => {
    observer?.disconnect();
    observer = null;
  };
  // The element may come later than the component (a card column that waits for a card).
  watch(
    el,
    (now) => {
      stop();
      if (now && typeof ResizeObserver === "function") {
        observer = new ResizeObserver(() => changed());
        observer.observe(now);
      }
    },
    { immediate: true, flush: "post" },
  );
  onBeforeUnmount(stop);
}
