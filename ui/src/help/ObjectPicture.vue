<script setup lang="ts">
// What an object is: our map with a car station (us) and two objects that we send, a repeater with its frequency and a meeting point; the arrows take them to the maps of two other stations.
import { CALLS } from "@/help/calls";
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpMap from "@/help/HelpMap.vue";
import HelpStation from "@/help/HelpStation.vue";
import HelpSymbol from "@/help/HelpSymbol.vue";
import { arrow, waves } from "@/help/draw";

const others = [14, 82];
</script>

<template>
  <HelpFrame name="object">
    <HelpMap :x="3" :y="12" :w="170" :h="126">
      <HelpStation table="/" code=">" :x="44" :y="96" :label="t('help.me')" />
      <path class="hp-flow" :d="waves(60, 96, -20, 2, 8, 5)" />
      <HelpStation table="/" code="r" :x="112" :y="48" :label="CALLS.repeater" />
      <HelpStation table="\" code=";" :x="140" :y="102" />
    </HelpMap>
    <template v-for="y in others" :key="y">
      <path class="hp-flow" :d="arrow(176, 75, 202, y + 28)" />
      <HelpMap :x="204" :y="y" :w="73" :h="56">
        <HelpSymbol table="/" code="-" :x="220" :y="y + 38" :size="18" />
        <HelpSymbol table="/" code="r" :x="244" :y="y + 20" :size="18" />
        <HelpSymbol table="\" code=";" :x="262" :y="y + 38" :size="18" />
      </HelpMap>
    </template>
  </HelpFrame>
</template>
