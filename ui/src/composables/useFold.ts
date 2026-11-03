// The fold of a group or a box of the Settings tab (SettingsGroup, SettingsBox): open or folded, kept in this browser for each id (lib/storage.ts, `settings.fold.ID`, open when nothing is kept), opened by itself when it has something the
// person must see (`show` turns true: a complaint of the daemon about one of its fields, a radio that is not connected) and when the page leads to a control inside it (lib/attention.ts sends REVEAL_EVENT to the control before it scrolls and focuses),
// and never closed but by the person. One pattern for both, so that the page has one kind of fold.
import { onBeforeUnmount, onMounted, watch, type Ref } from "vue";
import { usePersistedFlag } from "@/composables/usePersisted";
import { REVEAL_EVENT } from "@/lib/attention";

export function useFold(id: string, show: () => boolean, root: Readonly<Ref<HTMLElement | null>>) {
  const open = usePersistedFlag(`settings.fold.${id}`, ["open", "folded"], true);
  const reveal = (): void => {
    open.value = true;
  };
  watch(show, (wanted) => wanted && reveal(), { immediate: true });
  onMounted(() => root.value?.addEventListener(REVEAL_EVENT, reveal));
  onBeforeUnmount(() => root.value?.removeEventListener(REVEAL_EVENT, reveal));
  return { open };
}
