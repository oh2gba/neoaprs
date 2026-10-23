<script setup lang="ts">
// An APRS symbol as a picture: the sprite of the table and code, with the overlay character over it for an overlay table. A symbol that is none is a small dot.
import { computed } from "vue";
import { layerStyle, symbolLayers } from "@/lib/symbols";

const props = withDefaults(defineProps<{ table: string; code: string; size?: number }>(), { size: 22 });
const layers = computed(() => symbolLayers(props.table, props.code).map((layer) => layerStyle(layer, props.size)));
</script>

<template>
  <span class="symicon" :class="{ 'stn-plain': layers.length === 0 }" :style="{ width: `${size}px`, height: `${size}px` }" aria-hidden="true">
    <span v-for="(style, i) in layers" :key="i" class="stn-layer" :style="style"></span>
  </span>
</template>
