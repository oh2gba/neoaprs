<script setup lang="ts">
// The small (i) that explains what a control is for: closed until it is pressed, then a note that opens under it (above it where there is no room below), fixed in the window and kept wholly inside it (moved sideways where it would run off an edge, as on a phone; lib/infotip.ts `placeNote`), above the map and not clipped by the panel: the slot (the sentences of the note, one `info-line` each). One note is open at a time; Esc, a click or tap outside
// it, or the focus moving away closes it. The note is text, not a tooltip: it works with a finger and with the keyboard. `label` is the name of the button for a screen reader ("About Path"). `picture` adds a small
// drawing under the text (help/pictures.ts; its description for a screen reader is in the catalogue), for a note that a picture explains better than words.
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { usePopup } from "@/composables/usePopup";
import type { PictureName } from "@/help/names";
import { PICTURES } from "@/help/pictures";
import { newTipId, openTip, placeNote } from "@/lib/infotip";

defineProps<{ label: string; picture?: PictureName }>();

const id = newTipId();
const root = ref<HTMLElement | null>(null);
const button = ref<HTMLButtonElement | null>(null);
const note = ref<HTMLElement | null>(null);
const open = computed(() => openTip.value === id);
/** Where the note stands, in the window: it is fixed, so that the panel, the pane and the map do not clip it, and it is above the map. */
const spot = ref<{ left: number; top: number; width: number } | null>(null);

function place(): void {
  const trigger = button.value?.getBoundingClientRect();
  const box = note.value;
  if (!trigger || !box) return;
  const width = box.offsetWidth || box.getBoundingClientRect().width;
  const height = box.offsetHeight || box.getBoundingClientRect().height;
  spot.value = placeNote(trigger, { width, height }, { width: document.documentElement.clientWidth, height: document.documentElement.clientHeight });
}

function close(): void {
  if (openTip.value === id) openTip.value = null;
}

const popup = usePopup({ open, root, trigger: button, close, escapeAnywhere: true });

watch(open, async (now) => {
  if (!now) {
    window.removeEventListener("scroll", place, true);
    window.removeEventListener("resize", place);
    return;
  }
  spot.value = null;
  await nextTick();
  place();
  window.addEventListener("scroll", place, true); // (a pane that scrolls under an open note takes the note with it)
  window.addEventListener("resize", place);
});
onBeforeUnmount(() => {
  window.removeEventListener("scroll", place, true);
  window.removeEventListener("resize", place);
  close();
});
</script>

<template>
  <span ref="root" class="infotip" @keydown="popup.onEscape">
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
    <span
      v-if="open"
      :id="`${id}-note`"
      ref="note"
      class="info-text"
      :class="{ 'with-picture': picture }"
      role="note"
      :style="spot === null ? { visibility: 'hidden' } : { left: `${spot.left}px`, top: `${spot.top}px`, width: `${spot.width}px` }"
      ><slot></slot><template v-if="picture"><component :is="PICTURES[picture]" /></template
    ></span>
  </span>
</template>
