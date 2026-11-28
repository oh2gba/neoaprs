// The fold of a Settings group or box: open or folded, kept in the browser per id (`first` when
// nothing is kept, open unless said). It opens by itself when `show` turns true or when the page leads to a control
// inside it (REVEAL_EVENT from lib/attention.ts), and closes only by the person.
import { onBeforeUnmount, onMounted, watch, type Ref } from "vue";
import { usePersistedFlag } from "@/composables/usePersisted";
import { REVEAL_EVENT } from "@/lib/attention";

export function useFold(id: string, show: () => boolean, root: Readonly<Ref<HTMLElement | null>>, first = true) {
  const open = usePersistedFlag(`settings.fold.${id}`, ["open", "folded"], first);
  const reveal = (): void => {
    open.value = true;
  };
  watch(show, (wanted) => wanted && reveal(), { immediate: true });
  onMounted(() => root.value?.addEventListener(REVEAL_EVENT, reveal));
  onBeforeUnmount(() => root.value?.removeEventListener(REVEAL_EVENT, reveal));
  return { open };
}
