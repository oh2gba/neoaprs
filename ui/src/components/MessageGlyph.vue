<script setup lang="ts">
// The one picture for "message" (an envelope), drawn in SVG with the colour of the text, so that it follows the light or dark scheme: the Message button of a row of the Stations table (IconButton kind "message", which uses it), the "Message OH2XYZ" button
// under an empty result, and the mark on the messages not seen in the header are all this one. For a new place that says "message" use this (or IconButton kind="message" for a small button) and not a character or a picture of its own. It is decoration: the
// button or the text beside it names the thing (aria-hidden).
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
