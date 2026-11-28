<script setup lang="ts">
// Three ways a packet reaches our radio: straight from a station, through a digipeater, and from
// APRS-IS through an iGate that puts it on the air. The last is crossed out: what Show Internet
// packets heard by radio leaves out when unticked.
import { CALLS } from "@/help/calls";
import { arrow, waves } from "@/help/draw";
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpLabel from "@/help/HelpLabel.vue";
import HelpStation from "@/help/HelpStation.vue";
</script>

<template>
  <HelpFrame name="gated">
    <HelpStation table="/" code=">" :x="34" :y="22" :size="22" :label="CALLS.otherCar" />
    <path class="hp-flow" :d="waves(50, 22, 0, 2, 7, 5)" />
    <path class="hp-flow" :d="arrow(66, 26, 214, 60)" />

    <HelpStation table="/" code="-" :x="34" :y="70" :size="22" :label="CALLS.other" />
    <path class="hp-flow" :d="arrow(50, 70, 106, 70)" />
    <HelpStation table="2" code="#" :x="124" :y="70" :size="22" :label="CALLS.digipeater" />
    <path class="hp-flow" :d="arrow(142, 70, 214, 70)" />

    <g transform="translate(-178 38)">
      <path class="hp-card" d="M196 98a14 14 0 0 1-2-27 18 18 0 0 1 34-4 15 15 0 0 1 22 13 13 13 0 0 1-2 18z" />
      <HelpLabel :x="223" :y="90" :text="CALLS.aprsIs" />
    </g>
    <path class="hp-dim" :d="arrow(76, 122, 106, 122)" />
    <HelpStation table="I" code="&" :x="124" :y="122" :size="22" :label="CALLS.igate" />
    <path class="hp-dim hp-dash" d="M142 118L214 80" />
    <path class="hp-bad" d="M171 92l14 14m0-14l-14 14" />

    <!-- left of the edge by half the longest name of this station in the catalogues -->
    <HelpStation table="/" code="-" :x="238" :y="70" :size="30" :label="t('help.me')" />
  </HelpFrame>
</template>
