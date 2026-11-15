// The scope of a radio's box: the fold's state (remembered in this browser for that radio, folded at first) and whether the box asks for the rows, which is while the fold is open, its picture has room, the radio has a scope
// now and the page's counting of who looks (composables/useScopeLooks.ts) asks for them at all. The rows themselves are drawn by components/HfWaterfall.vue, and the receive level is components/HfLevelBar.vue's. The
// fold's key carries the radio's id (as the boxes' own folds do, components/RadioBox.vue).
import { computed, ref } from "vue";
import { usePersistedFlag } from "@/composables/usePersisted";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { fieldId, type RadioId } from "@/lib/radios";

export function useHfScope(radio: RadioId) {
  const { scope } = useDaemonContext();
  const open = usePersistedFlag(`settings.fold.${fieldId(`radio/${radio}/scope`)}`, ["open", "folded"], false);
  const shown = ref(false); // the canvas has room (components/HfWaterfall.vue says): a fold that is open under another tab shows nothing
  const available = computed(() => scope.has(radio));
  scope.look(
    () => open.value && shown.value && available.value,
    () => radio,
  );
  return { radio, open, shown, available, wanted: computed(() => open.value && scope.asked.value.includes(radio)) };
}
