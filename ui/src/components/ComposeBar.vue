<script setup lang="ts">
// The box to write in, the same on every tab: fixed at the bottom of the tab, the list above it scrolling. The fields are the default slot; under them one line with, at its right, the counter ("12 left", red and "3 over"
// when the text is too long; none when `left` is not given) and then the buttons (slot `buttons`: the secondary one, Cancel, left of the primary one, which is rightmost). The slot `aside` is what goes at the left of that line
// (Pick on the map). `scrolls` is for a form so tall that on a phone its fields scroll inside the bar, the line with the buttons always in view. A phone's keyboard must not hide the field being typed in: the field is
// brought into view when it takes the focus. The form sends `submit` (Enter in a field, or the button of type submit). `inline` is the box of one field, in a line with the counter and the button (the Messages tab's: the field grows, the rest is as wide as it is).
import { leftText } from "@/lib/compose";

defineProps<{ label: string; left?: number; leftTitle?: string; scrolls?: boolean; inline?: boolean }>();
const emit = defineEmits<{ submit: [] }>();

/** The on-screen keyboard takes a moment to come up; then the field being typed in is scrolled into view (the page is as high as the window that is left: 100dvh). */
function seen(event: FocusEvent): void {
  const field = event.target;
  if (field instanceof HTMLElement) window.setTimeout(() => field.scrollIntoView?.({ block: "nearest" }), 300);
}
</script>

<template>
  <form class="composebar" :class="{ scrolls }" :aria-label="label" @submit.prevent="emit('submit')" @focusin="seen">
    <div class="composebar-fields" :class="{ grow: inline }"><slot /></div>
    <div class="composebar-foot">
      <div class="composebar-aside"><slot name="aside" /></div>
      <span v-if="left !== undefined" class="compose-left mono" :class="{ over: left < 0 }" :title="leftTitle">{{ leftText(left) }}</span>
      <slot name="buttons" />
    </div>
  </form>
</template>
