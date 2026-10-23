<script setup lang="ts">
// The small (i) after the label of a field that a word cannot explain: a button that opens a short note (a few plain sentences and an example) under the field. One note is open at a time; Esc, a click or tap
// outside it, or the focus moving away closes it. The note is text, not a tooltip: it works with a finger and with the keyboard.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { newTipId, openTip } from "@/lib/infotip";

defineProps<{ label: string; text: string; example?: string }>();

const id = newTipId();
const root = ref<HTMLElement | null>(null);
const button = ref<HTMLButtonElement | null>(null);
const open = computed(() => openTip.value === id);

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

watch(open, listen);
onBeforeUnmount(() => {
  listen(false);
  close();
});
</script>

<template>
  <span ref="root" class="infotip">
    <button
      ref="button"
      class="infotip-button"
      type="button"
      :aria-expanded="open"
      :aria-controls="`${id}-note`"
      :aria-label="`About ${label}`"
      @click="openTip = open ? null : id"
    >
      i
    </button>
    <span v-if="open" :id="`${id}-note`" class="infotip-note" role="note">
      {{ text }}
      <span v-if="example" class="infotip-example">
        Example: <code>{{ example }}</code>
      </span>
    </span>
  </span>
</template>
