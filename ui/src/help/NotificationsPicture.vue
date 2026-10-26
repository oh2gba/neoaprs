<script setup lang="ts">
// An alert for a new message: a station's message arrives, and this device plays a sound (the speaker) and shows a pop-up (the card).
import { CALLS } from "@/help/calls";
import { arrow, waves } from "@/help/draw";
import HelpBubble from "@/help/HelpBubble.vue";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpStation from "@/help/HelpStation.vue";
</script>

<template>
  <HelpFrame name="notifications">
    <HelpStation table="/" code=">" :x="34" :y="64" :label="CALLS.otherCar" />
    <HelpBubble :x="62" :y="30" :w="48" text="QRU" :lit="true" />
    <path class="hp-flow" :d="arrow(122, 56, 156, 36)" />
    <path class="hp-flow" :d="arrow(122, 66, 156, 108)" />
    <path class="hp-solid" d="M170 22h8l11-9v26l-11-9h-8z" />
    <path class="hp-flow" :d="waves(192, 26, 0, 2, 8, 6)" />
    <rect class="hp-card" x="162" y="86" width="104" height="44" rx="6" />
    <path class="hp-dim" d="M172 98h40M172 108h66M172 118h52" />
    <circle class="hp-fill" cx="252" cy="98" r="4" />
  </HelpFrame>
</template>
