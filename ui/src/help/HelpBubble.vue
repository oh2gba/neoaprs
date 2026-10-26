<script setup lang="ts">
// A speech bubble in a picture with a short text that is the same in every language ("QRU", "QRV 145.500"), its tail under the left end. `lit` draws it in the accent colour: the one that is sent.
defineProps<{ x: number; y: number; w: number; text: string; lit?: boolean }>();
</script>

<template>
  <g>
    <path class="hp-card" :class="{ 'hp-lit': lit }" :d="`M${x + 8} ${y + 20}l-3 7 11-7`" />
    <rect class="hp-card" :class="{ 'hp-lit': lit }" :x="x" :y="y" :width="w" height="20" rx="7" />
    <text class="hp-label" :x="x + w / 2" :y="y + 14">{{ text }}</text>
  </g>
</template>
