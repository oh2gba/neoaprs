<script setup lang="ts">
// The access key: typed once on a phone (the dots in the field), after which the phone stays logged in (the tick).
import { arrow } from "@/help/draw";
import HelpFrame from "@/help/HelpFrame.vue";

const dots = [0, 1, 2, 3, 4, 5];
</script>

<template>
  <HelpFrame name="accesskey">
    <circle class="hp-flow" cx="34" cy="58" r="12" />
    <path class="hp-flow" d="M46 58H88M72 58v10M82 58v8" />
    <path class="hp-flow" :d="arrow(98, 58, 142, 58)" />
    <rect class="hp-solid" x="152" y="8" width="76" height="134" rx="10" />
    <rect class="hp-map" x="158" y="22" width="64" height="106" rx="3" />
    <rect class="hp-card hp-lit" x="164" y="44" width="52" height="20" rx="4" />
    <circle v-for="i in dots" :key="i" class="hp-fill" :cx="172 + i * 7.5" cy="54" r="2" />
    <rect class="hp-fill" x="172" y="78" width="36" height="14" rx="4" />
    <path class="hp-ok" d="M244 104l8 8 16-18" />
  </HelpFrame>
</template>
