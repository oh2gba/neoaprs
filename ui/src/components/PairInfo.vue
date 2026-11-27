<script setup lang="ts">
// The (i) in a pair's box (Settings, Digipeater) that opens what the pair does, with pictures: a
// station that puts the pair's call in its path is sent on once on the other radio, and one
// without it stops at your station. The line of the slow radio's limit is there only when one of
// the two is an HF or LoRa radio. The (i) is the notes' own button, without a hover text.
import { ref } from "vue";
import ExplainDialog from "@/components/ExplainDialog.vue";
import PairPicture from "@/components/PairPicture.vue";
import { t } from "@/i18n";
import { LIMITS } from "@/protocol/lists";

const props = defineProps<{ first: string; second: string; call: string; slow: readonly string[] }>();
const button = ref<HTMLButtonElement | null>(null);
const open = ref(false);
const lines = (): string[] => [
  t("settings.pair.explain.line1", { call: props.call }),
  t("settings.pair.explain.line2"),
  t("settings.pair.explain.line3", { call: props.call }),
];
</script>

<template>
  <button
    ref="button"
    type="button"
    class="info-toggle"
    :aria-expanded="open"
    :aria-label="t('settings.pair.explain.label', { first, second })"
    @click="open = true"
    v-text="'i'"
  ></button>
  <Teleport v-if="open" to="body">
    <ExplainDialog :title="t('settings.pair.explain.title', { first, second })" :opener="button" @close="open = false">
      <PairPicture :first="first" :second="second" :call="call" />
      <p v-for="line in lines()" :key="line">{{ line }}</p>
      <PairPicture :first="first" :second="second" :call="call" stopped />
      <p v-for="radio in slow" :key="radio" class="muted">
        {{ t("settings.pair.explain.slow", { radio, n: LIMITS.pass.slowMax, min: LIMITS.pass.slowWindowMin }) }}
      </p>
    </ExplainDialog>
  </Teleport>
</template>
