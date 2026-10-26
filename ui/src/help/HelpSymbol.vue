<script setup lang="ts">
// An APRS symbol in a picture, cut out of the same sheets as the map's markers (lib/symbols.ts), `size` px wide and centred on (x, y).
import { computed } from "vue";
import { SPRITE_COLUMNS, SPRITE_PX, SPRITE_ROWS, sheetUrl, symbolLayers } from "@/lib/symbols";

const props = withDefaults(defineProps<{ table: string; code: string; x: number; y: number; size?: number }>(), { size: 26 });
const layers = computed(() => symbolLayers(props.table, props.code));
</script>

<template>
  <svg
    v-for="(layer, i) in layers"
    :key="i"
    :x="x - size / 2"
    :y="y - size / 2"
    :width="size"
    :height="size"
    :viewBox="`${layer.column * SPRITE_PX} ${layer.row * SPRITE_PX} ${SPRITE_PX} ${SPRITE_PX}`"
  >
    <image :href="sheetUrl(layer.sheet)" :width="SPRITE_COLUMNS * SPRITE_PX" :height="SPRITE_ROWS * SPRITE_PX" />
  </svg>
</template>
