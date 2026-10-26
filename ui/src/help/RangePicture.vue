<script setup lang="ts">
// A digipeater's range: the circle it reaches; the stations inside it are heard through it (solid line), the ones outside are not (dashed line, crossed).
import { CALLS } from "@/help/calls";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpLabel from "@/help/HelpLabel.vue";
import HelpStation from "@/help/HelpStation.vue";

const inside = [
  { code: "-", x: 98, y: 52 },
  { code: ">", x: 190, y: 108 },
  { code: "-", x: 98, y: 114 },
];
const outside = [
  { code: ">", x: 256, y: 36 },
  { code: "-", x: 26, y: 100 },
];
</script>

<template>
  <HelpFrame name="range">
    <circle class="hp-wash" cx="140" cy="80" r="58" />
    <template v-for="s in inside" :key="s.x">
      <path class="hp-ok" :d="`M140 80L${s.x} ${s.y}`" />
      <HelpStation table="/" :code="s.code" :x="s.x" :y="s.y" :size="22" />
    </template>
    <template v-for="s in outside" :key="s.x">
      <path class="hp-dim hp-dash" :d="`M140 80L${s.x} ${s.y}`" />
      <HelpStation table="/" :code="s.code" :x="s.x" :y="s.y" :size="22" faded />
      <path class="hp-bad" :d="`M${s.x - 5} ${s.y + 17}l10 10m0-10l-10 10`" />
    </template>
    <rect class="hp-card" x="125" y="65" width="30" height="30" rx="6" />
    <HelpStation table="/" code="#" :x="140" :y="80" :size="28" />
    <HelpLabel :x="140" :y="13" :text="CALLS.digipeater" />
  </HelpFrame>
</template>
