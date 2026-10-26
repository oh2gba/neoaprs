<script setup lang="ts">
// The (i) at the top right of a tab that says what the tab is for and how it is used (InfoTip, with its picture): a thin bar of its own over the tab, as the Email tab has its (i) at the end of its bar; the note opens leftward from the corner.
import InfoTip from "@/components/InfoTip.vue";
import type { PictureName } from "@/help/names";

defineProps<{ label: string; picture?: PictureName }>();
</script>

<template>
  <div class="tab-help">
    <InfoTip :label="label" :picture="picture"><slot></slot></InfoTip>
  </div>
</template>
