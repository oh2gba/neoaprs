<script setup lang="ts">
// Receive only: the stations that APRS-IS has within the map's radius come to our map, one way. Nothing goes back, and nothing of it goes on the air.
import { CALLS } from "@/help/calls";
import { arrow } from "@/help/draw";
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpLabel from "@/help/HelpLabel.vue";
import HelpMap from "@/help/HelpMap.vue";
import HelpStation from "@/help/HelpStation.vue";
</script>

<template>
  <HelpFrame name="internet">
    <path class="hp-card" d="M14 86a14 14 0 0 1-2-27 18 18 0 0 1 34-4 15 15 0 0 1 22 13 13 13 0 0 1-2 18z" />
    <HelpLabel :x="42" :y="78" :text="CALLS.aprsIs" />
    <path class="hp-flow" :d="arrow(82, 70, 128, 70)" />
    <HelpMap :x="136" :y="10" :w="134" :h="130">
      <circle class="hp-wash" cx="204" cy="75" r="50" />
      <HelpStation table="/" code="-" :x="204" :y="75" :size="28" :label="t('help.me')" />
      <circle class="hp-dim hp-dash" cx="172" cy="46" r="13" />
      <HelpStation table="/" code=">" :x="172" :y="46" :size="22" />
      <circle class="hp-dim hp-dash" cx="254" cy="120" r="13" />
      <HelpStation table="/" code="-" :x="254" :y="120" :size="22" />
      <HelpStation table="/" code=">" :x="244" :y="30" :size="22" :faded="true" />
    </HelpMap>
  </HelpFrame>
</template>
