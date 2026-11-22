<script setup lang="ts">
// The counter for a text with a limit, used on every field that has one: "12 left", orange "3
// over" when the limit shrank under the text, and the title "12 of 67 bytes left". Its room is
// kept for the widest text it can say (`max`: "67 left" or "67 over") by laying both under it
// unseen (`data-room`, `data-over`), so that the field beside it keeps its width.
import { computed } from "vue";
import { leftText } from "@/lib/compose";

const props = defineProps<{ left: number; max: number; title?: string }>();

/** The widest text the counter says: the full limit left, and as many over. */
const room = computed(() => leftText(props.max));
const over = computed(() => leftText(-props.max));
</script>

<template>
  <span class="compose-left mono" :class="{ over: left < 0 }" :data-room="room" :data-over="over" :title="title">{{ leftText(left) }}</span>
</template>
