<script setup lang="ts">
// Local info (QRU): this station asks QRU by radio, and a server station near it answers with objects (a repeater and an event), which appear on the map.
import { CALLS } from "@/help/calls";
import HelpBubble from "@/help/HelpBubble.vue";
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpStation from "@/help/HelpStation.vue";
import HelpSymbol from "@/help/HelpSymbol.vue";
import { arrow, waves } from "@/help/draw";
</script>

<template>
  <HelpFrame name="qru">
    <HelpStation table="/" code=">" :x="46" :y="62" :label="t('help.me')" />
    <HelpBubble :x="113" :y="8" :w="46" text="QRU" />
    <path class="hp-flow" :d="waves(74, 40, 0, 2, 8, 5)" />
    <path class="hp-flow" :d="arrow(90, 44, 206, 44)" />
    <path class="hp-flow" :d="arrow(206, 74, 90, 74)" />
    <rect class="hp-card" x="104" y="60" width="28" height="28" rx="6" />
    <HelpSymbol table="/" code="r" :x="118" :y="74" :size="22" />
    <rect class="hp-card" x="146" y="60" width="28" height="28" rx="6" />
    <HelpSymbol table="/" code=";" :x="160" :y="74" :size="22" />
    <HelpStation table="/" code="K" :x="236" :y="44" :size="30" :label="CALLS.server" />
  </HelpFrame>
</template>
