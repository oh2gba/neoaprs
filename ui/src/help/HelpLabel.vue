<script setup lang="ts">
// A short label in a picture that is the same in every language (a call, a frequency, WIDE2-1), centred on x, or starting at x with `start`; `onAccent` is for one on an accent-coloured dot.
defineProps<{ x: number; y: number; text: string; start?: boolean; onAccent?: boolean }>();
</script>

<template>
  <text class="hp-label" :class="{ 'hp-label-start': start, 'hp-on-accent': onAccent }" :x="x" :y="y">{{ text }}</text>
</template>
