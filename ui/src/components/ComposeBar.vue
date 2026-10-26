<script setup lang="ts">
// The box to write in, the same on every tab that has a form. A form of fields is a group box (fieldset and legend, the look of the Settings groups): the legend is `label`, the fields are the default slot, and under them one line
// with, at its right, the counter ("12 left", red and "3 over" when the text is too long; none when `left` is not given) and then the buttons (slot `buttons`: the secondary one, Cancel, left of the primary one, which is rightmost).
// The slot `aside` is what goes at the left of that line (no form has anything there now; the space keeps the counter and the buttons at the right). `inline` is the chat line under a conversation (the Messages tab's): no box and
// no legend, one field that grows, the counter and the button in the same line, fixed at the bottom of the conversation. A phone's keyboard must not hide the field being typed in: the field is
// brought into view when it takes the focus. The form sends `submit` (Enter in a field, or the button of type submit).
import { leftText } from "@/lib/compose";

defineProps<{ label: string; left?: number; leftTitle?: string; inline?: boolean }>();
const emit = defineEmits<{ submit: [] }>();

/** The on-screen keyboard takes a moment to come up; then the field being typed in is scrolled into view (the page is as high as the window that is left: 100dvh). */
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
        <span v-if="left !== undefined" class="compose-left mono" :class="{ over: left < 0 }" :title="leftTitle">{{ leftText(left) }}</span>
        <slot name="buttons" />
      </div>
    </component>
  </form>
</template>
