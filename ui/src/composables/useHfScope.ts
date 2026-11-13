// The scope of the HF radio's box: the fold's state (remembered in this browser, folded at first) and whether the box asks for the rows, which is while the fold is open, its picture has room and the page's counting of who looks (composables/useScopeLooks.ts)
// asks for them at all. The rows themselves are drawn by components/HfWaterfall.vue, and the receive level is components/HfLevelBar.vue's.
import { computed, ref } from "vue";
import { usePersistedFlag } from "@/composables/usePersisted";
import { useDaemonContext } from "@/composables/useDaemonContext";

export function useHfScope() {
  const { scope } = useDaemonContext();
  const open = usePersistedFlag("settings.fold.hf-scope", ["open", "folded"], false);
  const shown = ref(false); // the canvas has room (components/HfWaterfall.vue says): a fold that is open under another tab shows nothing
  scope.look(() => open.value && shown.value && scope.available.value);
  return { open, shown, available: scope.available, wanted: computed(() => open.value && scope.wanted.value) };
}
