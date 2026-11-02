<script setup lang="ts">
// A station with two radios: the FM radio reaches the car and the digipeater nearby by short waves along the ground, the HF radio a distant station by the signal that goes up and comes down (the Mercury picture's arc over the dashed line).
import { CALLS } from "@/help/calls";
import { waves } from "@/help/draw";
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpStation from "@/help/HelpStation.vue";
</script>

<template>
  <HelpFrame name="tworadios">
    <path class="hp-dim hp-dash" d="M8 22h264" />
    <HelpStation table="/" code="-" :x="34" :y="104" :size="26" :label="t('help.me')" />
    <HelpStation table="/" code=">" :x="104" :y="124" :size="20" :label="CALLS.car" />
    <HelpStation table="2" code="#" :x="156" :y="124" :size="20" :label="CALLS.digipeater" />
    <path class="hp-flow" :d="waves(52, 118, 18, 2, 9, 6)" />
    <path class="hp-flow" d="M52 94Q140 -8 228 94" />
    <path class="hp-flow" :d="waves(52, 94, -50, 2, 8, 5)" />
    <path class="hp-flow" :d="waves(228, 94, -130, 2, 8, 5)" />
    <HelpStation table="/" code="-" :x="246" :y="104" :size="26" :label="CALLS.other" />
  </HelpFrame>
</template>
