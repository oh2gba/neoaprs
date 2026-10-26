<script setup lang="ts">
// The Dummy radio: no radio, made-up stations (dashed) that answer, and nothing that goes out on the air (crossed).
import { CALLS } from "@/help/calls";
import { arrow, waves } from "@/help/draw";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpStation from "@/help/HelpStation.vue";
</script>

<template>
  <HelpFrame name="dummy">
    <rect class="hp-dim hp-dash" x="10" y="14" width="104" height="122" rx="10" />
    <HelpStation table="/" code=">" :x="40" :y="46" :size="24" :label="CALLS.otherCar" />
    <HelpStation table="/" code="-" :x="84" :y="46" :size="24" :label="CALLS.other" />
    <HelpStation table="/" code="#" :x="62" :y="104" :size="24" :label="CALLS.digipeater" />
    <path class="hp-flow" :d="arrow(122, 75, 168, 75)" />
    <HelpStation table="/" code="-" :x="196" :y="75" :size="30" :label="CALLS.me" />
    <path class="hp-dim hp-dash" :d="waves(216, 75, 0, 3, 8, 6)" />
    <path class="hp-bad" d="M242 62l14 26m0-26l-14 26" />
  </HelpFrame>
</template>
