<script setup lang="ts">
// Network access: the computer NeoAPRS runs on and, over the network, the phone, the tablet and the laptop that open its page.
import { arrow, waves } from "@/help/draw";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpSymbol from "@/help/HelpSymbol.vue";

const devices = [
  { x: 214, y: 10, w: 26, h: 44 },
  { x: 196, y: 62, w: 62, h: 34 },
  { x: 188, y: 104, w: 78, h: 34 },
];
</script>

<template>
  <HelpFrame name="network">
    <rect class="hp-solid" x="12" y="45" width="58" height="46" rx="5" />
    <HelpSymbol table="/" code="L" :x="41" :y="68" :size="32" />
    <path class="hp-flow" :d="waves(78, 68, 0, 3, 8, 6)" />
    <template v-for="d in devices" :key="d.y">
      <path class="hp-flow" :d="arrow(122, 68, d.x - 8, d.y + d.h / 2)" />
      <rect class="hp-solid" :x="d.x" :y="d.y" :width="d.w" :height="d.h" rx="5" />
      <rect class="hp-map" :x="d.x + 4" :y="d.y + 4" :width="d.w - 8" :height="d.h - 8" rx="2" />
      <circle class="hp-fill" :cx="d.x + d.w / 2" :cy="d.y + d.h / 2" r="3" />
    </template>
  </HelpFrame>
</template>
