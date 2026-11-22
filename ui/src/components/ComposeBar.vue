<script setup lang="ts">
// The form box used on every tab that has a form: a fieldset with `label` as legend, the fields
// in the default slot, and a line with the counter (LeftCounter, room kept for `leftMax`) and
// the buttons (slot `buttons`, primary rightmost). The slot `aside` fills the left of that line.
// `inline` is the chat line under a conversation: no box or legend, one growing field. The
// focused field is scrolled into view so that a phone keyboard does not hide it. The form emits
// `submit`.
import LeftCounter from "@/components/LeftCounter.vue";

defineProps<{ label: string; left?: number; leftMax?: number; leftTitle?: string; inline?: boolean }>();
const emit = defineEmits<{ submit: [] }>();

/** Wait for the on-screen keyboard, then scroll the focused field into view (the page is 100dvh
 * high). */
function seen(event: FocusEvent): void {
  const field = event.target;
  if (field instanceof HTMLElement) window.setTimeout(() => field.scrollIntoView?.({ block: "nearest" }), 300);
}
</script>

<template>
  <form class="composebar" :class="{ boxed: !inline }" :aria-label="label" @submit.prevent="emit('submit')" @focusin="seen">
    <component :is="inline ? 'div' : 'fieldset'" class="composebox">
      <legend v-if="!inline">{{ label }}</legend>
      <div class="composebar-fields" :class="{ grow: inline }"><slot /></div>
      <div class="composebar-foot">
        <div v-if="!inline" class="composebar-aside"><slot name="aside" /></div>
        <LeftCounter v-if="left !== undefined" :left="left" :max="leftMax ?? Math.max(left, 0)" :title="leftTitle" />
        <slot name="buttons" />
      </div>
    </component>
  </form>
</template>
