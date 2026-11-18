<script setup lang="ts">
// A layer's mark, 16 px (lib/layers/marks.ts): the shape the map draws it with, in the same token, so that the Layers box is the map's legend. It says nothing to a screen reader: the row's name does.
import { computed } from "vue";
import { MARKS, MARK_SIZE, type MarkName } from "@/lib/layers/marks";

const props = defineProps<{ name: MarkName }>();
const mark = computed(() => MARKS[props.name]);
const ink = computed(() => `var(${mark.value.token})`);
</script>

<template>
  <svg class="layermark" :width="MARK_SIZE" :height="MARK_SIZE" :viewBox="`0 0 ${MARK_SIZE} ${MARK_SIZE}`" aria-hidden="true" focusable="false">
    <path
      :d="mark.d"
      :fill="mark.fill ? ink : 'none'"
      :stroke="mark.fill ? 'none' : ink"
      :stroke-width="mark.fill ? undefined : 1.5"
      :stroke-dasharray="mark.dash"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  </svg>
</template>
