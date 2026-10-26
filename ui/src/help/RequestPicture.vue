<script setup lang="ts">
// "Send only when asked": the object is kept and not beaconed (the dashed box); a station asks with QRU and our station answers with the object.
import { CALLS } from "@/help/calls";
import HelpBubble from "@/help/HelpBubble.vue";
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpStation from "@/help/HelpStation.vue";
import HelpSymbol from "@/help/HelpSymbol.vue";
import { arrow } from "@/help/draw";
</script>

<template>
  <HelpFrame name="request">
    <HelpStation table="/" code=">" :x="34" :y="62" :label="CALLS.otherCar" />
    <HelpBubble :x="113" :y="8" :w="46" text="QRU" />
    <path class="hp-flow" :d="arrow(68, 44, 206, 44)" />
    <path class="hp-flow" :d="arrow(206, 74, 68, 74)" />
    <rect class="hp-card" x="122" y="60" width="28" height="28" rx="6" />
    <HelpSymbol table="/" code="r" :x="136" :y="74" :size="22" />
    <HelpStation table="/" code="-" :x="236" :y="44" :size="30" :label="t('help.me')" />
    <rect class="hp-card hp-dash" x="222" y="86" width="44" height="34" rx="6" />
    <HelpSymbol table="/" code="r" :x="244" :y="103" :size="22" />
  </HelpFrame>
</template>
