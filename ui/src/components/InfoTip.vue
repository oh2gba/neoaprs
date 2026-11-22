<script setup lang="ts">
// The small (i) that explains a control: a note opens under it (above where there is no room),
// fixed in the window and kept inside it (lib/infotip.ts `placeNote`). The slot holds the
// sentences, one `info-line` each. One note is open at a time; Esc, a click outside or the focus
// moving away closes it. `picture` adds a small drawing (help/pictures.ts).
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
/** The note's position in the window; fixed so that panels and the map do not clip it. */
const spot = ref<{ left: number; top: number; width: number } | null>(null);

function place(): void {
  const trigger = button.value?.getBoundingClientRect();
  const box = note.value;
  if (!trigger || !box) return;
  const width = box.offsetWidth || box.getBoundingClientRect().width;
  const height = box.offsetHeight || box.getBoundingClientRect().height;
  spot.value = placeNote(
    trigger,
    { width, height },
    { width: document.documentElement.clientWidth, height: document.documentElement.clientHeight },
  );
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
  if (openTip.value !== id) return;
  place();
  window.addEventListener("scroll", place, true); // follow a pane that scrolls under an open note
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
      :style="
        spot === null
          ? { visibility: 'hidden' }
          : { left: `${spot.left}px`, top: `${spot.top}px`, width: `${spot.width}px` }
      "
      ><slot></slot><template v-if="picture"><component :is="PICTURES[picture]" /></template
    ></span>
  </span>
</template>
