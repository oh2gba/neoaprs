<script setup lang="ts">
// A piece of map in a picture: the page's background with two faint roads, cut off at its frame; what is drawn in its slot is in the picture's own coordinates.
defineProps<{ x: number; y: number; w: number; h: number }>();
</script>

<template>
  <svg :x="x" :y="y" :width="w" :height="h" :viewBox="`${x} ${y} ${w} ${h}`">
    <rect :x="x" :y="y" :width="w" :height="h" class="hp-map" />
    <path
      class="hp-road"
      :d="`M${x - 4} ${y + h * 0.72}Q${x + w * 0.45} ${y + h * 0.3} ${x + w + 4} ${y + h * 0.58}M${x + w * 0.28} ${y - 4}L${x + w * 0.5} ${y + h + 4}`"
    />
    <slot></slot>
    <rect :x="x + 0.75" :y="y + 0.75" :width="w - 1.5" :height="h - 1.5" rx="5" class="hp-frame" />
  </svg>
</template>
