<script setup lang="ts">
// The HF radio's scope: a distant station sends (waves), and the spectrum of the audio shows its frame as a block of bars over the low ripple of the noise, with the receive level under it as a bar in the good range.
import { CALLS } from "@/help/calls";
import { waves } from "@/help/draw";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpStation from "@/help/HelpStation.vue";

const noise = "M20 96l8-5 8 4 8-6 8 5 8-3 8 4 8-5 8 3 8-4 8 5 8-3 8 4 8-6 8 5 8-4 8 4 8-5 8 3 8-4 8 5 8-3 8 3";
const block = "M96 96l0-34 10-6 10 3 10-5 10 4 10-4 10 5 10-3 0 40";
</script>

<template>
  <HelpFrame name="scope">
    <HelpStation table="/" code="-" :x="244" :y="30" :size="26" :label="CALLS.other" />
    <path class="hp-flow" :d="waves(228, 30, 180, 2, 8, 5)" />
    <path class="hp-frame" d="M16 98h250" />
    <path class="hp-dim" :d="noise" />
    <path class="hp-wash" :d="block" />
    <rect class="hp-frame" x="20" y="116" width="240" height="14" rx="3" />
    <rect class="hp-ok" x="80" y="116" width="90" height="14" rx="3" />
    <path class="hp-lit" d="M120 112v22" />
  </HelpFrame>
</template>
