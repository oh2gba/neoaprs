<script setup lang="ts">
// The scope of a radio's box, folded under one row (DisclosureBox, remembered per radio): the
// waterfall from 300 to 2700 Hz (HfWaterfall.vue) and the receive level (HfLevelBar.vue). Rows
// are requested from the daemon only while the fold is open (composables/useHfScope.ts); a radio
// with no scope, or that is off, has none and this is not drawn.
import DisclosureBox from "@/components/DisclosureBox.vue";
import HfLevelBar from "@/components/HfLevelBar.vue";
import HfWaterfall from "@/components/HfWaterfall.vue";
import { useHfScope } from "@/composables/useHfScope";
import { t } from "@/i18n";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import type { PageRadio, RadioId } from "@/lib/radios";

const props = defineProps<{ radio: RadioId; card?: { radio: PageRadio; form: SettingsFormState } }>();
const scope = useHfScope(props.radio);
</script>

<template>
  <DisclosureBox
    v-if="scope.available.value"
    class="hf-scope"
    :title="t('settings.scope.title')"
    :open="scope.open.value"
    @folded="scope.open.value = $event"
  >
    <div class="scope-picture">
      <HfWaterfall :radio="scope.radio" @reach="scope.reach.value = $event" @shown="scope.shown.value = $event" />
    </div>
    <HfLevelBar :on="scope.wanted.value" :radio="scope.radio" tip :card="card" />
  </DisclosureBox>
</template>

<style scoped>
.scope-picture {
  height: 240px; /* forty seconds of waterfall over the curve */
  margin-bottom: 8px;
  overflow: hidden;
  background: var(--waterfall-0);
  border: 1px solid var(--border);
  border-radius: 4px;
}
</style>
