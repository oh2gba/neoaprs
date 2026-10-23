// A list that is oldest first and shows the newest at its bottom, like the Messages tab: it is scrolled to the end when it is shown and whenever `source` changes (a row is added), and `toNewest()` does it on demand (a
// form that opened under the list has made it shorter). `el` is the element that scrolls.
import { nextTick, onMounted, watch, type Ref, type WatchSource } from "vue";

export function useToNewest(el: Ref<HTMLElement | null>, source: WatchSource): () => Promise<void> {
  async function toNewest(): Promise<void> {
    await nextTick();
    if (el.value) el.value.scrollTop = el.value.scrollHeight;
  }
  onMounted(toNewest);
  watch(source, toNewest);
  return toNewest;
}
