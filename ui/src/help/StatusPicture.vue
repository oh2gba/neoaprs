<script setup lang="ts">
// The status: a short text that we write once; on the map of the others it stands after our call.
import HelpBubble from "@/help/HelpBubble.vue";
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpLabel from "@/help/HelpLabel.vue";
import HelpMap from "@/help/HelpMap.vue";
import HelpStation from "@/help/HelpStation.vue";
import { arrow, waves } from "@/help/draw";
</script>

<template>
  <HelpFrame name="status">
    <HelpBubble :x="8" :y="26" :w="100" text="QRV 145.500" lit />
    <HelpStation table="/" code="-" :x="44" :y="86" :size="30" :label="t('help.me')" />
    <path class="hp-flow" :d="waves(62, 86, 0, 2, 8, 5)" />
    <path class="hp-flow" :d="arrow(84, 86, 126, 86)" />
    <HelpMap :x="132" :y="12" :w="146" :h="126">
      <HelpStation table="/" code="-" :x="205" :y="50" :size="30" />
      <HelpLabel :x="205" :y="76" :text="t('help.me')" />
      <rect class="hp-card hp-lit" x="146" y="88" width="118" height="22" rx="5" />
      <HelpLabel :x="205" :y="103" text="QRV 145.500" />
    </HelpMap>
  </HelpFrame>
</template>
