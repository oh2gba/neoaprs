<script setup lang="ts">
// The Mercury HF modem: our station and a distant one, far apart, the signal going up and coming down between them (the ionosphere's arc); each has waves of its own, and a station without the modem (dashed) hears nothing.
import { CALLS } from "@/help/calls";
import { waves } from "@/help/draw";
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpStation from "@/help/HelpStation.vue";
</script>

<template>
  <HelpFrame name="mercury">
    <path class="hp-dim hp-dash" d="M8 128h264" />
    <HelpStation table="/" code="-" :x="40" :y="100" :size="26" :label="t('help.me')" />
    <HelpStation table="/" code="-" :x="240" :y="100" :size="26" :label="CALLS.other" />
    <path class="hp-flow" d="M56 92Q140 -10 224 92" />
    <path class="hp-flow" :d="waves(56, 92, -50, 2, 8, 5)" />
    <path class="hp-flow" :d="waves(224, 92, -130, 2, 8, 5)" />
    <path class="hp-dim hp-dash" d="M8 22h264" />
    <HelpStation table="/" code=">" :x="140" :y="104" :size="20" :label="CALLS.otherCar" faded />
    <path class="hp-bad" d="M152 86l10 10m0-10l-10 10" />
  </HelpFrame>
</template>
