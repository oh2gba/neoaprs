<script setup lang="ts">
// The symbol: the choice among many (a car is picked) and the same symbol on the map of the others, under our call.
import { arrow } from "@/help/draw";
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpMap from "@/help/HelpMap.vue";
import HelpStation from "@/help/HelpStation.vue";
import HelpSymbol from "@/help/HelpSymbol.vue";

const choices = [
  ["-", "/"],
  [">", "/"],
  ["_", "/"],
  ["#", "/"],
  ["[", "/"],
  ["b", "/"],
  ["s", "/"],
  ["^", "/"],
  ["l", "/"],
].map(([code, table], i) => ({ code: code ?? "", table: table ?? "/", x: 34 + (i % 3) * 38, y: 38 + Math.floor(i / 3) * 38 }));
</script>

<template>
  <HelpFrame name="symbol">
    <rect class="hp-card" x="9" y="15" width="124" height="120" rx="6" />
    <rect class="hp-card hp-lit" x="56" y="22" width="32" height="32" rx="5" />
    <HelpSymbol v-for="c in choices" :key="c.x + c.y" :table="c.table" :code="c.code" :x="c.x" :y="c.y" :size="26" />
    <path class="hp-flow" :d="arrow(138, 75, 164, 75)" />
    <HelpMap :x="170" :y="15" :w="106" :h="120">
      <HelpStation table="/" code=">" :x="223" :y="64" :size="30" :label="t('help.me')" />
    </HelpMap>
  </HelpFrame>
</template>
