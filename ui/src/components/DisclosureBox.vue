<script setup lang="ts">
// A heading that opens and closes what is under it. It starts closed, or open when `open` is
// true, and opens when `open` later turns true; only the person closes it. `plain` leaves the
// look to the caller's class and `summaryClass` styles the heading line. `folded` reports the
// new state. The slot `summary` replaces the heading line when it is more than the title.
import { ref, watch } from "vue";

const emit = defineEmits<{ folded: [open: boolean] }>();
const props = withDefaults(defineProps<{ title?: string; open?: boolean; plain?: boolean; summaryClass?: string | Record<string, boolean> }>(), {
  title: "",
  open: false,
  plain: false,
  summaryClass: undefined,
});
const shown = ref(props.open);
watch(
  () => props.open,
  (open) => {
    if (open) shown.value = true;
  },
);

function toggled(event: Event): void {
  if (event.target instanceof HTMLDetailsElement) {
    shown.value = event.target.open;
    emit("folded", shown.value);
  }
}
</script>

<template>
  <details :class="{ disclosure: !plain }" :open="shown" @toggle="toggled">
    <summary :class="summaryClass">
      <slot name="summary">{{ title }}</slot>
    </summary>
    <slot v-if="plain" />
    <div v-else class="disclosure-body"><slot /></div>
  </details>
</template>
