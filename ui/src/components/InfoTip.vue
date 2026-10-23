<script setup lang="ts">
// The small (i) that explains what a control is for: closed until it is pressed, then a note that opens downward from it, kept inside the page (moved sideways where it would run off an edge, as on a phone): the slot (the sentences of the note, one `info-line` each). One note is open at a time; Esc, a click or tap outside
// it, or the focus moving away closes it. The note is text, not a tooltip: it works with a finger and with the keyboard. `label` is the name of the button for a screen reader ("About Path").
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { newTipId, openTip } from "@/lib/infotip";

defineProps<{ label: string }>();

const id = newTipId();
const root = ref<HTMLElement | null>(null);
const button = ref<HTMLButtonElement | null>(null);
const note = ref<HTMLElement | null>(null);
const open = computed(() => openTip.value === id);
/** How far the note is moved sideways to be wholly in the page, px. */
const shift = ref(0);
const MARGIN = 8;

/** Moves the note left where it runs past the right edge, then right where that took it past the left one. */
function place(): void {
  const box = note.value?.getBoundingClientRect();
  if (!box) return;
  const right = document.documentElement.clientWidth - MARGIN;
  const base = box.left - shift.value;
  const edge = base + box.width;
  shift.value = Math.max(MARGIN - base, Math.min(0, right - edge));
}

function close(): void {
  if (openTip.value === id) openTip.value = null;
}

function away(event: Event): void {
  if (!(event.target instanceof Node) || !root.value?.contains(event.target)) close();
}

function onKey(event: KeyboardEvent): void {
  if (event.key !== "Escape") return;
  close();
  button.value?.focus();
}

function listen(on: boolean): void {
  const act = (type: string, handler: EventListener): void => (on ? document.addEventListener(type, handler) : document.removeEventListener(type, handler));
  act("pointerdown", away);
  act("focusin", away);
  act("keydown", onKey as EventListener);
}

watch(open, async (now) => {
  listen(now);
  if (!now) return;
  shift.value = 0;
  await nextTick();
  place();
});
onBeforeUnmount(() => {
  listen(false);
  close();
});
</script>

<template>
  <span ref="root" class="infotip" @keydown.esc="close">
    <button
      ref="button"
      type="button"
      class="info-toggle"
      :aria-expanded="open"
      :aria-controls="`${id}-note`"
      :aria-label="label"
      :title="label"
      @click="openTip = open ? null : id"
      v-text="'i'"
    ></button>
    <span v-if="open" :id="`${id}-note`" ref="note" class="info-text" role="note" :style="shift === 0 ? undefined : { transform: `translateX(${shift}px)` }"
      ><slot></slot
    ></span>
  </span>
</template>
