<script setup lang="ts">
// What a bulletin is: one station sends, and the same message is on the board of every station that hears it.
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpLabel from "@/help/HelpLabel.vue";
import HelpStation from "@/help/HelpStation.vue";
import { arrow, waves } from "@/help/draw";

const boards = [8, 56, 104];
</script>

<template>
  <HelpFrame name="bulletin">
    <HelpStation table="/" code="-" :x="44" :y="56" :size="30" :label="t('help.me')" />
    <path class="hp-flow" :d="waves(62, 56, 0, 2, 8, 5)" />
    <rect class="hp-card hp-lit" x="9" y="92" width="54" height="40" rx="5" />
    <HelpLabel :x="36" :y="105" text="BLN1" />
    <path class="hp-dim" d="M16 114h40M16 124h28" />
    <template v-for="(y, i) in boards" :key="y">
      <path class="hp-flow" :d="arrow(80, 56, 112, y + 18)" />
      <HelpStation table="/" :code="i === 1 ? '>' : '-'" :x="126" :y="y + 18" :size="24" />
      <rect class="hp-card hp-lit" :x="148" :y="y" width="128" height="36" rx="5" />
      <HelpLabel :x="156" :y="y + 14" text="BLN1" start />
      <path class="hp-dim" :d="`M156 ${y + 22}h104M156 ${y + 29}h64`" />
    </template>
  </HelpFrame>
</template>
