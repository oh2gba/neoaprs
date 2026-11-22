<script setup lang="ts">
// The (i) at the top right of a tab, saying what the tab is for (InfoTip, with its picture): a
// thin bar over the tab; the note opens leftward from the corner.
import InfoTip from "@/components/InfoTip.vue";
import type { PictureName } from "@/help/names";

defineProps<{ label: string; picture?: PictureName }>();
</script>

<template>
  <div class="tab-help">
    <InfoTip :label="label" :picture="picture"><slot></slot></InfoTip>
  </div>
</template>
