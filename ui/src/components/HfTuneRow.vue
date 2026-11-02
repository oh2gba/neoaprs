<script setup lang="ts">
// The Tune button of the HF radio, an ActionRow under the Sound card and Keying fields: it keys the radio through the keying in use and sends a steady tone through the sound card for ten seconds (composables/useHfTests.ts), for tuning the antenna,
// setting the audio level and finding which sound device is the radio. While the tone is on the button reads Stop, in the room it already has (TwoWords: nothing moves), and a press stops it early; the status line of the box says Tuning… meanwhile.
import ActionRow from "@/components/ActionRow.vue";
import TwoWords from "@/components/TwoWords.vue";
import { useHfTests } from "@/composables/useHfTests";
import { t } from "@/i18n";

defineProps<{ id: string }>();
const tests = useHfTests();
</script>

<template>
  <ActionRow :id="id" :label="t('settings.tune.label')" :tip-label="t('settings.tune.tip_label')">
    <button :id="id" class="btn" type="button" :disabled="tests.tuneOff.value" :title="tests.why.value" @click="tests.tune">
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
