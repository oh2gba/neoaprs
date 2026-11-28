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
    <path class="hp-flow" :d="arrow(66, 26, 222, 60)" />

    <HelpStation table="/" code="-" :x="34" :y="70" :size="22" :label="CALLS.other" />
    <path class="hp-flow" :d="arrow(50, 70, 106, 70)" />
    <HelpStation table="2" code="#" :x="124" :y="70" :size="22" :label="CALLS.digipeater" />
    <path class="hp-flow" :d="arrow(142, 70, 222, 70)" />

    <g transform="translate(-178 32)">
      <path class="hp-card" d="M196 98a14 14 0 0 1-2-27 18 18 0 0 1 34-4 15 15 0 0 1 22 13 13 13 0 0 1-2 18z" />
      <HelpLabel :x="223" :y="90" :text="CALLS.aprsIs" />
    </g>
    <path class="hp-dim" :d="arrow(76, 116, 106, 116)" />
    <HelpStation table="I" code="&" :x="124" :y="116" :size="22" :label="CALLS.igate" />
    <path class="hp-dim hp-dash" d="M142 112L222 82" />
    <path class="hp-bad" d="M175 90l14 14m0-14l-14 14" />

    <HelpStation table="/" code="-" :x="246" :y="70" :size="30" :label="t('help.me')" />
  </HelpFrame>
</template>
