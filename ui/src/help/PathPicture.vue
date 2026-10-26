<script setup lang="ts">
// The path: our packet is repeated by the fill-in digipeater (WIDE1-1) and then by a wide-area one (WIDE2-1), two hops, before the other stations hear it; the path as it is written is under the chain.
import { CALLS } from "@/help/calls";
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpLabel from "@/help/HelpLabel.vue";
import HelpStation from "@/help/HelpStation.vue";
import { arrow } from "@/help/draw";

const hops = [
  { from: 64, to: 100, n: "1" },
  { from: 134, to: 168, n: "2" },
  { from: 200, to: 228, n: "" },
];
</script>

<template>
  <HelpFrame name="path">
    <HelpStation table="/" code=">" :x="44" :y="44" :label="t('help.me')" />
    <HelpStation table="1" code="#" :x="118" :y="44" :label="CALLS.fillIn" />
    <HelpStation table="2" code="#" :x="184" :y="44" :label="CALLS.wide" />
    <HelpStation table="/" code="-" :x="246" :y="44" :label="CALLS.other" />
    <template v-for="hop in hops" :key="hop.from">
      <path class="hp-flow" :d="arrow(hop.from, 44, hop.to, 44)" />
      <template v-if="hop.n">
        <circle class="hp-fill" :cx="(hop.from + hop.to) / 2" cy="26" r="7" />
        <HelpLabel :x="(hop.from + hop.to) / 2" :y="30" :text="hop.n" on-accent />
      </template>
    </template>
    <rect class="hp-card hp-lit" x="72" y="96" width="136" height="24" rx="12" />
    <HelpLabel :x="140" :y="112" text="WIDE1-1,WIDE2-1" />
  </HelpFrame>
</template>
