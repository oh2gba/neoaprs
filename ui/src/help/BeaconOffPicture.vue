<script setup lang="ts">
// Beacon Off and Beacon now: above, the clock sends nothing (empty beacons on the time line); below, a press of the button sends one beacon all the same.
import { arrow, waves } from "@/help/draw";
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpStation from "@/help/HelpStation.vue";

const beacons = [34, 112, 190];
</script>

<template>
  <HelpFrame name="beaconoff">
    <path class="hp-dim" d="M14 36H266" />
    <template v-for="x in beacons" :key="x">
      <circle class="hp-dim hp-dash" :cx="x" cy="36" r="5" />
      <circle class="hp-card" :cx="x + 39" cy="36" r="9" />
      <path :d="`M${x + 39} 30v6l4 3`" />
    </template>
    <path class="hp-bad" d="M236 24l16 24m0-24l-16 24" />
    <rect class="hp-card hp-lit" x="20" y="88" width="64" height="30" rx="8" />
    <circle class="hp-fill" cx="52" cy="103" r="6" />
    <path class="hp-flow" :d="arrow(92, 103, 138, 103)" />
    <HelpStation table="/" code="-" :x="164" :y="103" :size="30" :label="t('help.me')" />
    <path class="hp-flow" :d="waves(184, 103, 0, 3, 8, 6)" />
  </HelpFrame>
</template>
