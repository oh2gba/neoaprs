<script setup lang="ts">
// The map radius: the world map is everywhere, the detailed map (streets, with their names) only within the radius around our station.
import { arrow } from "@/help/draw";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpMap from "@/help/HelpMap.vue";
import HelpSymbol from "@/help/HelpSymbol.vue";
</script>

<template>
  <HelpFrame name="radius">
    <HelpMap :x="8" :y="10" :w="264" :h="130">
      <clipPath id="hp-radius-clip"><circle cx="140" cy="75" r="52" /></clipPath>
      <circle class="hp-wash" cx="140" cy="75" r="52" />
      <g clip-path="url(#hp-radius-clip)">
        <path class="hp-dim" d="M80 50H200M80 75H200M80 100H200M110 25V125M140 25V125M170 25V125" />
      </g>
      <path class="hp-flow" :d="arrow(140, 75, 192, 75)" />
      <HelpSymbol table="/" code="-" :x="140" :y="75" :size="26" />
    </HelpMap>
  </HelpFrame>
</template>
