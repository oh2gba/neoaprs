<script setup lang="ts">
// A row of the Settings tab and of the setup guide whose control is an action button (Download map, Check now, Download logs): its own label, the button at the left edge of the control column like the fields', the (i) after it, and the quiet lines of its
// outcome (progress, "Map downloaded 21 Oct", "Saved FILE.") under it in the same column. A button that belongs to a field (the Test of the command, Refresh of the port, the new access key) stays beside that field and is not a row.
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
