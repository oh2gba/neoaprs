<script setup lang="ts">
// The call and its SSID: one call sign for several stations, told apart by the number after it (-9 a car, -10 an iGate).
import { CALLS } from "@/help/calls";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpLabel from "@/help/HelpLabel.vue";
import HelpStation from "@/help/HelpStation.vue";

const stations = [
  { x: 44, table: "/", code: "-", label: CALLS.me },
  { x: 140, table: "/", code: ">", label: CALLS.car },
  { x: 236, table: "I", code: "&", label: CALLS.iGateCall },
];
</script>

<template>
  <HelpFrame name="ssid">
    <rect class="hp-card hp-lit" x="92" y="12" width="96" height="26" rx="13" />
    <HelpLabel :x="140" :y="29" :text="CALLS.me" />
    <template v-for="s in stations" :key="s.x">
      <path class="hp-dim" :d="`M140 38V50H${s.x}V70`" />
      <HelpStation :table="s.table" :code="s.code" :x="s.x" :y="86" :size="30" :label="s.label" />
    </template>
  </HelpFrame>
</template>
