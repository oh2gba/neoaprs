// The scope of a radio's box: the fold state (remembered per radio, folded at first) and whether
// the box asks for rows, which it does while the fold is open, the picture has room, the radio
// has a scope and the page's look counting (`useScopeLooks`) asks for them.
import { computed, ref } from "vue";
import { usePersistedFlag } from "@/composables/usePersisted";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { fieldId, type RadioId } from "@/lib/radios";

export function useHfScope(radio: RadioId) {
  const { scope } = useDaemonContext();
  const open = usePersistedFlag(`settings.fold.${fieldId(`radio/${radio}/scope`)}`, ["open", "folded"], false);
  const shown = ref(false);
  const reach = ref(0);
  const available = computed(() => scope.has(radio));
  scope.look(
    () => open.value && shown.value && available.value,
    () => radio,
    () => reach.value,
  );
  return {
    radio,
    open,
    shown,
    reach,
    available,
    wanted: computed(() => open.value && scope.asked.value.includes(radio)),
  };
}
