<script setup lang="ts">
// The counter of a text with a limit, the one on every field that has one (the box to write a message in, the Bulletins, Email, Objects and HF tests boxes, the comment and the status of the My station tab):
// "12 left", orange "3 over" when the limit shrank under a text (the padlock, a power, a course), and the title "12 of 67 bytes left". Its room is kept for the widest it can say (`max`: "67 left", or
// "67 over"): both are laid under it unseen (`data-room` and `data-over`, two lines of the style's ::before), so that the field beside it does not change width while the number goes from two digits to one, whatever the
// letters of the language are as wide as.
import { computed } from "vue";
import { leftText } from "@/lib/compose";

const props = defineProps<{ left: number; max: number; title?: string }>();

/** The widest the counter says: the full limit left, and as many over. */
const room = computed(() => leftText(props.max));
const over = computed(() => leftText(-props.max));
</script>

<template>
  <span class="compose-left mono" :class="{ over: left < 0 }" :data-room="room" :data-over="over" :title="title">{{ leftText(left) }}</span>
</template>
