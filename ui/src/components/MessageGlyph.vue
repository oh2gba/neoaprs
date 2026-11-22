<script setup lang="ts">
// The one picture for "message" (an envelope), drawn in SVG in the text colour. IconButton kind
// "message", the Message button under an empty result and the unseen-count mark in the header
// all use it; a new place that means "message" should too. It is decoration (aria-hidden).
withDefaults(defineProps<{ size?: number }>(), { size: 16 });
</script>

<template>
  <svg
    class="msgglyph"
    :width="size"
    :height="size"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path d="M2 3.5h12v9H2zM2.5 4l5.5 4.5L13.5 4" />
  </svg>
</template>
