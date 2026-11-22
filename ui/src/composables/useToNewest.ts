// A list that is oldest first and shows the newest at its bottom, like the Messages tab: it is
// scrolled to the end when shown and whenever `source` changes, and `toNewest()` does it on
// demand. It stays pinned to the end while its size changes afterwards (a tab shown, late
// fonts), unless the person has scrolled up to read: then it stays until the next change of
// `source`. `el` is the element that scrolls.
import { nextTick, onBeforeUnmount, onMounted, watch, type Ref, type WatchSource } from "vue";

// This close to the end still counts as "at the newest".
const NEAR_END_PX = 24;

export function useToNewest(el: Ref<HTMLElement | null>, source: WatchSource): () => Promise<void> {
  let pinned = true;
  let observer: ResizeObserver | null = null;

  function scrollToEnd(): void {
    if (el.value) el.value.scrollTop = el.value.scrollHeight;
  }

  async function toNewest(): Promise<void> {
    pinned = true;
    await nextTick();
    scrollToEnd();
    requestAnimationFrame(scrollToEnd);
  }

  function onScroll(): void {
    const box = el.value;
    if (box) pinned = box.scrollHeight - box.scrollTop - box.clientHeight <= NEAR_END_PX;
  }

  function observe(box: HTMLElement): void {
    box.addEventListener("scroll", onScroll, { passive: true });
    if (typeof ResizeObserver === "undefined") return;
    observer = new ResizeObserver(() => {
      if (pinned) scrollToEnd();
    });
    observer.observe(box);
    for (const child of Array.from(box.children)) observer.observe(child);
  }

  onMounted(() => {
    if (el.value) observe(el.value);
    void toNewest();
  });
  onBeforeUnmount(() => {
    observer?.disconnect();
    el.value?.removeEventListener("scroll", onScroll);
  });
  watch(source, () => {
    if (el.value && observer) for (const child of Array.from(el.value.children)) observer.observe(child);
    void toNewest();
  });
  return toNewest;
}
