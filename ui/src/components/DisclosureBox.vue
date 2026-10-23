<script setup lang="ts">
// A heading that opens and closes what is under it, for what most people never need. It starts closed, or open when `open` is true, and opens when `open` turns true later; it is never closed by the page, only by the person.
// The look is the page's heading that opens (`disclosure`); `plain` leaves the look to the class the caller gives it (a card's Details, the Raw of a packet, the preview of the beacon), and `summaryClass` is a class of the heading line.
import { ref, watch } from "vue";

const props = withDefaults(defineProps<{ title: string; open?: boolean; plain?: boolean; summaryClass?: string | Record<string, boolean> }>(), {
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
  if (event.target instanceof HTMLDetailsElement) shown.value = event.target.open;
}
</script>

<template>
  <details :class="{ disclosure: !plain }" :open="shown" @toggle="toggled">
    <summary :class="summaryClass">{{ title }}</summary>
    <slot v-if="plain" />
    <div v-else class="disclosure-body"><slot /></div>
  </details>
</template>
