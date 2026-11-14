<script setup lang="ts">
// The scope of the HF radio's box, folded away under one row (the page's fold, DisclosureBox, remembered in this browser): the waterfall of the radio's audio from 300 to 2700 Hz (components/HfWaterfall.vue: the ruler, the
// picture, the curve, the stations heard), and under it the receive level (components/HfLevelBar.vue). The monitor card over the map (components/MonitorCard.vue) shows the same larger. The rows are asked of the daemon only while
// the fold is open (composables/useHfScope.ts); a modem without the interface has no scope, and this is not there. The picture has a height of its own, so that nothing moves when the fold has drawn it.
import DisclosureBox from "@/components/DisclosureBox.vue";
import HfLevelBar from "@/components/HfLevelBar.vue";
import HfWaterfall from "@/components/HfWaterfall.vue";
import { useHfScope } from "@/composables/useHfScope";
import { t } from "@/i18n";

const scope = useHfScope();
</script>

<template>
  <DisclosureBox v-if="scope.available.value" class="hf-scope" :title="t('settings.scope.title')" :open="scope.open.value" @folded="scope.open.value = $event">
    <div class="scope-picture"><HfWaterfall @shown="scope.shown.value = $event" /></div>
    <HfLevelBar :on="scope.wanted.value" tip />
  </DisclosureBox>
</template>

<style scoped>
.scope-picture {
  height: 240px; /* forty seconds of the waterfall over the curve: the box in Settings */
  margin-bottom: 8px;
  overflow: hidden;
  background: var(--waterfall-0);
  border: 1px solid var(--border);
  border-radius: 4px;
}
</style>
