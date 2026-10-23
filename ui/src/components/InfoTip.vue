<script setup lang="ts">
// A small (i) that explains what a control is for: closed until it is clicked, then a few sentences (the slot) in a box that opens downward from it, kept inside the page (moved left where it would run off the right edge, as on a phone); Escape, a click anywhere
// else or the (i) again closes it.
import { nextTick, onBeforeUnmount, ref, useTemplateRef, watch } from "vue";

defineProps<{ label: string }>();
const open = ref(false);
const root = useTemplateRef<HTMLElement>("root");
const box = useTemplateRef<HTMLElement>("box");
/** How far the box is moved sideways from the (i), in px: 0 until it is measured. */
const shift = ref(0);
const MARGIN = 8;

/** Puts the box wholly in the page: at the (i)'s left edge when it fits there, else as far left as it needs, never past the left margin. */
function place(): void {
  const tip = root.value;
  const text = box.value;
  if (!tip || !text) return;
  const left = tip.getBoundingClientRect().left;
  const right = document.documentElement.clientWidth - MARGIN;
  shift.value = Math.max(MARGIN - left, Math.min(0, right - text.offsetWidth - left));
}

function outside(event: Event): void {
  if (event.target instanceof Node && !root.value?.contains(event.target)) open.value = false;
}

watch(open, async (now) => {
  if (!now) {
    document.removeEventListener("pointerdown", outside);
    return;
  }
  document.addEventListener("pointerdown", outside);
  await nextTick();
  place();
});
onBeforeUnmount(() => document.removeEventListener("pointerdown", outside));
</script>

<template>
  <span ref="root" class="infotip" @keydown.esc="open = false">
    <button type="button" class="info-toggle" :aria-expanded="open" :aria-label="label" :title="label" @click="open = !open">i</button>
    <span v-if="open" ref="box" class="info-text" role="note" :style="{ left: `${shift}px` }"><slot /></span>
  </span>
</template>
