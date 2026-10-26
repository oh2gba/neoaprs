<script setup lang="ts">
// How a station was heard: on the radio (waves, RF), or over the internet (the cloud, APRS-IS, with the dotted outline of a station of the internet).
import { CALLS } from "@/help/calls";
import { arrow, waves } from "@/help/draw";
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpLabel from "@/help/HelpLabel.vue";
import HelpStation from "@/help/HelpStation.vue";
</script>

<template>
  <HelpFrame name="channels">
    <HelpStation table="/" code=">" :x="36" :y="38" :label="CALLS.otherCar" />
    <path class="hp-flow" :d="waves(54, 38, 0, 3, 8, 6)" />
    <path class="hp-flow" :d="arrow(100, 38, 150, 38)" />
    <HelpStation table="/" code="-" :x="176" :y="38" :size="28" :label="t('help.me')" />
    <rect class="hp-card" x="214" y="28" width="38" height="20" rx="10" />
    <HelpLabel :x="233" :y="42" text="RF" />
    <path class="hp-card" d="M20 124a11 11 0 0 1-2-21 14 14 0 0 1 27-3 12 12 0 0 1 17 10 10 10 0 0 1-2 14z" />
    <HelpLabel :x="42" :y="118" text="IS" />
    <path class="hp-flow" :d="arrow(82, 108, 150, 108)" />
    <circle class="hp-dim hp-dash" cx="176" cy="108" r="15" />
    <HelpStation table="/" code=">" :x="176" :y="108" :size="22" />
    <rect class="hp-card" x="214" y="98" width="58" height="20" rx="10" />
    <HelpLabel :x="243" :y="112" :text="CALLS.aprsIs" />
  </HelpFrame>
</template>
