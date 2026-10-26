<script setup lang="ts">
// The beacon: our station sends its position (waves) and shows on the map of the others; below, the time line: the position goes out again and again, a clock between two.
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpMap from "@/help/HelpMap.vue";
import HelpStation from "@/help/HelpStation.vue";
import { arrow, waves } from "@/help/draw";

const beacons = [34, 112, 190];
</script>

<template>
  <HelpFrame name="beacon">
    <HelpStation table="/" code=">" :x="44" :y="42" :label="t('help.me')" />
    <path class="hp-flow" :d="waves(62, 42, 0, 3, 8, 6)" />
    <path class="hp-flow" :d="arrow(100, 42, 140, 42)" />
    <HelpMap :x="146" :y="8" :w="130" :h="72">
      <HelpStation table="/" code=">" :x="212" :y="38" :label="t('help.me')" />
    </HelpMap>
    <path class="hp-dim" d="M14 120H266" />
    <template v-for="x in beacons" :key="x">
      <circle class="hp-fill" :cx="x" cy="120" r="5" />
      <path class="hp-flow" :d="waves(x, 120, -90, 2, 9, 6)" />
      <circle class="hp-card" :cx="x + 39" cy="120" r="9" />
      <path :d="`M${x + 39} 114v6l4 3`" />
    </template>
    <circle class="hp-fill" cx="268" cy="120" r="5" />
    <path class="hp-flow" :d="waves(268, 120, -90, 2, 9, 6)" />
  </HelpFrame>
</template>
