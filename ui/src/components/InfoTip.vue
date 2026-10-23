<script setup lang="ts">
// The small (i) that explains what a control is for: closed until it is pressed, then a note under it: the slot, or the `text` and, after it, an example. One note is open at a time; Esc, a click or tap outside
// it, or the focus moving away closes it. The note is text, not a tooltip: it works with a finger and with the keyboard. `label` is the name of the button for a screen reader ("About Path").
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { newTipId, openTip } from "@/lib/infotip";

defineProps<{ label: string; text?: string; example?: string }>();

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
      type="button"
      class="info-toggle"
      :aria-expanded="open"
      :aria-controls="`${id}-note`"
      :aria-label="label"
      :title="label"
      @click="openTip = open ? null : id"
    >
      i
    </button>
    <span v-if="open" :id="`${id}-note`" class="info-text" role="note">
      <slot>{{ text }}</slot>
      <span v-if="example" class="info-example">
        Example: <code>{{ example }}</code>
      </span>
    </span>
  </span>
</template>
