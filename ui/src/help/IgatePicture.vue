<script setup lang="ts">
// An iGate: the stations on the radio side, the iGate that passes their packets on, and the internet (APRS-IS) side, in both directions.
import { CALLS } from "@/help/calls";
import { arrow, waves } from "@/help/draw";
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpLabel from "@/help/HelpLabel.vue";
import HelpStation from "@/help/HelpStation.vue";
</script>

<template>
  <HelpFrame name="igate">
    <g transform="translate(0 -8)">
      <HelpStation table="/" code=">" :x="44" :y="62" :label="t('help.me')" />
      <path class="hp-flow" :d="waves(62, 62, 0, 2, 8, 5)" />
      <path class="hp-flow" :d="arrow(80, 56, 104, 56)" />
      <HelpStation table="I" code="&" :x="124" :y="62" :size="30" :label="CALLS.igate" />
      <path class="hp-flow" :d="arrow(148, 56, 186, 56)" />
      <path class="hp-flow" :d="arrow(186, 70, 148, 70)" />
      <path class="hp-card" d="M196 98a14 14 0 0 1-2-27 18 18 0 0 1 34-4 15 15 0 0 1 22 13 13 13 0 0 1-2 18z" />
      <HelpLabel :x="231" :y="90" :text="CALLS.aprsIs" />
    </g>
  </HelpFrame>
</template>
