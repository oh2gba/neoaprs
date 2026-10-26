<script setup lang="ts">
// Our digipeater: a station that cannot reach the wide-area digipeater by itself (crossed) is repeated by ours, which passes the packet on.
import { CALLS } from "@/help/calls";
import { arrow } from "@/help/draw";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpStation from "@/help/HelpStation.vue";
</script>

<template>
  <HelpFrame name="digipeater">
    <HelpStation table="/" code=">" :x="32" :y="82" :label="CALLS.otherCar" />
    <HelpStation table="/" code="#" :x="140" :y="82" :size="30" :label="CALLS.me" />
    <HelpStation table="2" code="#" :x="248" :y="82" :label="CALLS.wide" />
    <path class="hp-flow" :d="arrow(54, 76, 112, 76)" />
    <path class="hp-flow" :d="arrow(164, 76, 222, 76)" />
    <path class="hp-dim hp-dash" d="M40 62Q140 -4 240 62" />
    <path class="hp-bad" d="M133 23l14 14m0-14l-14 14" />
  </HelpFrame>
</template>
