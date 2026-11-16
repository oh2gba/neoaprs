<script setup lang="ts">
// The receive level of a Sound card radio, a row of its box: the level Direwolf hears now (its modem's `rx_level`, every two seconds and at each packet, on Direwolf's own scale, lib/soundcardlevel.ts), on the bar of components/LevelBar.vue.
// The row is there while Direwolf does not run, with its room kept, so that nothing moves when the level comes; the bar is dimmed while the radio transmits (or is tuned), when the level is the last one heard. Its (i) is
// the receive level's of the HF box: the same words hold for both.
import { computed, useId } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import LevelBar from "@/components/LevelBar.vue";
import { t } from "@/i18n";
import type { PageRadio } from "@/lib/radios";
import { GOOD_PERCENT, levelPercent, levelText, levelZone } from "@/lib/soundcardlevel";

const props = defineProps<{ radio: PageRadio }>();
const id = useId();
const modem = computed(() => props.radio.row.modem);
const level = computed(() => modem.value?.rx_level ?? null);
const zone = computed(() => (level.value === null ? "low" : levelZone(level.value)));
const fill = computed(() => (level.value === null ? 0 : levelPercent(level.value)));
const held = computed(() => modem.value !== null && (modem.value.keyed || modem.value.test !== ""));
</script>

<template>
  <LevelBar :id="id" :label="t('settings.scope.level')" :percent="fill" :zone="zone" :good="GOOD_PERCENT" :held="held" :value="levelText(level)"
    ><InfoTip :label="t('settings.scope.tip_label')"
      ><span class="info-line">{{ t("settings.scope.tip1") }}</span
      ><span class="info-line">{{ t("settings.scope.tip2") }}</span></InfoTip
    ></LevelBar
  >
</template>
