<script setup lang="ts">
// A small (i) that explains what a control is for: closed until it is clicked, then a few sentences (the slot) in a box under it; Escape or another click closes it.
import { ref } from "vue";

defineProps<{ label: string }>();
const open = ref(false);
</script>

<template>
  <span class="infotip" @keydown.esc="open = false">
    <button type="button" class="info-toggle" :aria-expanded="open" :aria-label="label" :title="label" @click="open = !open">i</button>
    <span v-if="open" class="info-text" role="note"><slot /></span>
  </span>
</template>
