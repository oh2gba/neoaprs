<script setup lang="ts">
// The Dummy radio: no radio, made-up stations (dashed) that answer, and nothing that goes out on the air (crossed).
import { CALLS } from "@/help/calls";
import { arrow, waves } from "@/help/draw";
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpStation from "@/help/HelpStation.vue";
</script>

<template>
  <HelpFrame name="dummy">
    <rect class="hp-dim hp-dash" x="6" y="14" width="128" height="122" rx="10" />
    <HelpStation table="/" code=">" :x="38" :y="46" :size="24" :label="CALLS.otherCar" />
    <HelpStation table="/" code="-" :x="102" :y="46" :size="24" :label="CALLS.other" />
    <HelpStation table="/" code="#" :x="70" :y="104" :size="24" :label="CALLS.digipeater" />
    <path class="hp-flow" :d="arrow(142, 75, 190, 75)" />
    <HelpStation table="/" code="-" :x="226" :y="75" :size="30" :label="t('help.me')" />
    <path class="hp-dim hp-dash" :d="waves(244, 75, 0, 2, 6, 5)" />
    <path class="hp-bad" d="M262 62l12 26m0-26l-12 26" />
  </HelpFrame>
</template>
