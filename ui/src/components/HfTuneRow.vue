<script setup lang="ts">
// The Tune button of the HF radio, in the row of its own under the Sound card and Keying fields where the FM radio has Find my radio: it keys the radio through the keying in use and sends a steady tone through the sound card for ten seconds (composables/useHfTests.ts),
// for tuning the antenna, setting the audio level and finding which sound device is the radio. While the tone is on the button reads Stop, in the room it already has (TwoWords: nothing moves), and a press stops it early; the status line of the box says Tuning… meanwhile.
import TwoWords from "@/components/TwoWords.vue";
import { useHfTests } from "@/composables/useHfTests";
import { t } from "@/i18n";

defineProps<{ id: string }>();
const tests = useHfTests();
</script>

<template>
  <div class="radiofind hftune">
    <button :id="id" class="btn" type="button" :disabled="tests.tuneOff.value" :title="tests.why.value" :aria-pressed="tests.tuning.value" @click="tests.tune">
      <TwoWords :second="tests.tuning.value">
        <template #first>{{ t("settings.tune") }}</template>
        <template #second>{{ t("settings.tune_stop") }}</template>
      </TwoWords>
    </button>
  </div>
</template>
