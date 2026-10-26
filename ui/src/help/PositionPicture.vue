<script setup lang="ts">
// Where the position comes from: fixed (a station that stays where it is) or a GPS (a station that moves, the beacon at the turns).
import { waves } from "@/help/draw";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpSymbol from "@/help/HelpSymbol.vue";

const track = [
  [168, 118],
  [190, 104],
  [214, 98],
  [232, 78],
  [238, 52],
];
</script>

<template>
  <HelpFrame name="position">
    <path class="hp-card hp-dash" d="M126 10V140" />
    <HelpSymbol table="/" code="-" :x="64" :y="76" :size="34" />
    <path class="hp-flow" :d="waves(84, 76, 0, 3, 8, 6)" />
    <path class="hp-dim hp-dash" d="M168 118Q214 124 220 98T238 52" />
    <circle v-for="p in track" :key="p.join()" class="hp-fill" :cx="p[0]" :cy="p[1]" r="3.5" />
    <HelpSymbol table="/" code=">" :x="248" :y="38" :size="26" />
    <HelpSymbol table="\" code="S" :x="168" :y="28" :size="24" />
    <path class="hp-dim hp-dash" d="M180 34L238 40" />
  </HelpFrame>
</template>
