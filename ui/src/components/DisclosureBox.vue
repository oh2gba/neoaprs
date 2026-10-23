<script setup lang="ts">
// A heading that opens and closes what is under it, for what most people never need. It starts closed, or open when `open` is true, and opens when `open` turns true later; it is never closed by the page, only by the person.
import { ref, watch } from "vue";

const props = withDefaults(defineProps<{ title: string; open?: boolean }>(), { open: false });
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
  <details class="disclosure" :open="shown" @toggle="toggled">
    <summary>{{ title }}</summary>
    <div class="disclosure-body"><slot /></div>
  </details>
</template>
