// Calls `changed` when the element (once it is there) changes size (the map, which a phone hides under the open tab and shows again, or whose panel is dragged: MapLibre has to be told, it only listens to the window). Without a ResizeObserver (a very old browser) the
// window's own resize event is all there is.
import { onBeforeUnmount, watch, type Ref } from "vue";

export function useResized(el: Readonly<Ref<Element | null>>, changed: () => void): void {
  let observer: ResizeObserver | null = null;
  const stop = (): void => {
    observer?.disconnect();
    observer = null;
  };
  // (the element may come later than the component: a card column that is not there until there is a card)
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
