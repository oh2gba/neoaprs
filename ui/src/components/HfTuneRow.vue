<script setup lang="ts">
// The Tune button of the HF radio, an ActionRow: it keys the radio and sends a steady tone
// through the sound card for ten seconds (composables/useHfTests.ts), for tuning the antenna and
// setting the audio level. While the tone plays it reads Stop in the same room (TwoWords).
import ActionRow from "@/components/ActionRow.vue";
import TwoWords from "@/components/TwoWords.vue";
import { useHfTests } from "@/composables/useHfTests";
import { t } from "@/i18n";
import type { PageRadio } from "@/lib/radios";

const props = defineProps<{ id: string; radio: PageRadio }>();
const tests = useHfTests(() => props.radio);
</script>

<template>
  <ActionRow :id="id" :label="t('settings.tune.label')" :tip-label="t('settings.tune.tip_label')">
    <button
      :id="id"
      class="btn"
      type="button"
      :disabled="tests.tuneOff.value"
      :title="tests.why.value"
      @click="tests.tune"
    >
      <TwoWords :second="tests.tuning.value">
        <template #first>{{ t("settings.tune") }}</template>
        <template #second>{{ t("settings.tune_stop") }}</template>
      </TwoWords>
    </button>
    <template #tip
      ><span class="info-line">{{ t("settings.tune.tip1") }}</span></template
    >
  </ActionRow>
</template>
