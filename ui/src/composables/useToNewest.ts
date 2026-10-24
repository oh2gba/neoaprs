// A list that is oldest first and shows the newest at its bottom, like the Messages tab: it is scrolled to the end when it is shown and whenever `source` changes (a row is added, another conversation is
// opened), and `toNewest()` does it on demand (a form that opened under the list has made it shorter). It stays pinned to the end while its size changes afterwards (a tab that was hidden is shown, the
// delivery chains or the fonts come in late), unless the person has scrolled up to read: then it is left where they are until the next change of `source`. `el` is the element that scrolls.
import { nextTick, onBeforeUnmount, onMounted, watch, type Ref, type WatchSource } from "vue";

const NEAR_END_PX = 24; // this close to the end still counts as "at the newest"

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
    requestAnimationFrame(scrollToEnd); // (after the browser has laid out what came in)
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
