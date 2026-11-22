<script setup lang="ts">
// A Settings row whose control is an action button, with its (i) and the quiet lines of its
// outcome (progress, result) under it in the same column. A button that belongs to a field stays
// beside that field and is not a row.
import InfoTip from "@/components/InfoTip.vue";
import type { PictureName } from "@/help/names";

defineProps<{ id: string; label: string; tipLabel: string; picture?: PictureName }>();
</script>

<template>
  <div class="field action-row">
    <label :for="id">{{ label }}</label>
    <div class="field-control">
      <slot></slot>
      <InfoTip :label="tipLabel" :picture="picture"><slot name="tip"></slot></InfoTip>
    </div>
    <div class="action-notes"><slot name="notes"></slot></div>
  </div>
</template>
