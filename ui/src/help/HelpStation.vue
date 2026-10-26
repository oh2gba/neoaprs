<script setup lang="ts">
// A station or an object in a picture: its symbol, as the map shows it, with the call (or the frequency) under it. `faded` is a station that is out of the picture's point (out of range).
import HelpSymbol from "@/help/HelpSymbol.vue";

withDefaults(defineProps<{ table: string; code: string; x: number; y: number; label?: string; size?: number; faded?: boolean }>(), { label: "", size: 26 });
</script>

<template>
  <g :class="{ 'hp-faded': faded }">
    <HelpSymbol :table="table" :code="code" :x="x" :y="y" :size="size" />
    <text v-if="label" class="hp-label" :x="x" :y="y + size / 2 + 11">{{ label }}</text>
  </g>
</template>
