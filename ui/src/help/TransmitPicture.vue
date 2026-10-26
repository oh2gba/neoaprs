<script setup lang="ts">
// RX only: our station hears the others (an arrow in), and what it would send goes nowhere (dashed, crossed out).
import { CALLS } from "@/help/calls";
import { arrow } from "@/help/draw";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpStation from "@/help/HelpStation.vue";
</script>

<template>
  <HelpFrame name="transmit">
    <HelpStation table="/" code="-" :x="48" :y="36" :size="30" :label="CALLS.me" />
    <path class="hp-dim hp-dash" :d="arrow(76, 32, 196, 32)" />
    <path class="hp-bad" d="M128 20l16 24m0-24l-16 24" />
    <HelpStation table="/" code=">" :x="232" :y="36" :label="CALLS.otherCar" />
    <HelpStation table="/" code="-" :x="48" :y="108" :size="30" :label="CALLS.me" />
    <path class="hp-flow" :d="arrow(206, 104, 78, 104)" />
    <HelpStation table="/" code=">" :x="232" :y="108" :label="CALLS.otherCar" />
  </HelpFrame>
</template>
