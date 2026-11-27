<script setup lang="ts">
// The picture of a pair's pop-up (PairInfo): a station on the first radio sends with the pair's
// call in its path; your station, the two radios in one box, sends it on once on the second
// radio with the call marked used. With `stopped`, the small picture: a path without the call
// stops at your station. Drawn in the help pictures' style (styles/helppictures.css); each box
// holds a radio's name, cut here to fit (never in the dialog's title), under a short word.
import { computed } from "vue";
import HelpLabel from "@/help/HelpLabel.vue";
import { arrow } from "@/help/draw";
import { t } from "@/i18n";

const props = defineProps<{ first: string; second: string; call: string; stopped?: boolean }>();
const NAME_MAX = 11;
const cut = (name: string): string => (name.length > NAME_MAX ? `${name.slice(0, NAME_MAX - 1)}…` : name);
const a = computed(() => cut(props.first));
const b = computed(() => cut(props.second));
</script>

<template>
  <svg
    v-if="!stopped"
    class="hp pairpic"
    viewBox="0 0 360 138"
    role="img"
    :aria-label="t('settings.pair.explain.picture', { first, second, call })"
  >
    <text class="hp-word" x="47" y="32">{{ t("settings.pair.explain.station") }}</text>
    <rect class="hp-card" x="4" y="38" width="86" height="32" rx="6" />
    <text class="hp-word hp-word-strong" x="47" y="58">{{ a }}</text>
    <rect class="hp-solid" x="4" y="78" width="118" height="20" rx="4" />
    <HelpLabel :x="63" :y="92" :text="`${call},WIDE2-2`" />
    <rect class="hp-frame" x="136" y="6" width="90" height="104" rx="8" />
    <text class="hp-word hp-word-strong" x="181" y="24">{{ t("settings.pair.explain.you") }}</text>
    <rect class="hp-card" x="144" y="34" width="74" height="28" rx="5" />
    <text class="hp-word" x="181" y="52">{{ a }}</text>
    <rect class="hp-card" x="144" y="72" width="74" height="28" rx="5" />
    <text class="hp-word" x="181" y="90">{{ b }}</text>
    <path class="hp-flow" :d="arrow(92, 54, 142, 48)" />
    <path class="hp-flow" :d="arrow(220, 86, 268, 86)" />
    <text class="hp-word" x="313" y="64">{{ t("settings.pair.explain.stations") }}</text>
    <rect class="hp-card" x="270" y="70" width="86" height="32" rx="6" />
    <text class="hp-word hp-word-strong" x="313" y="90">{{ b }}</text>
    <rect class="hp-solid" x="232" y="112" width="124" height="20" rx="4" />
    <HelpLabel :x="294" :y="126" :text="`${call}*,WIDE2-2`" />
  </svg>
  <svg
    v-else
    class="hp pairpic"
    viewBox="0 0 360 72"
    role="img"
    :aria-label="t('settings.pair.explain.picture_stop', { call })"
  >
    <text class="hp-word" x="47" y="12">{{ t("settings.pair.explain.station") }}</text>
    <rect class="hp-card" x="4" y="16" width="86" height="28" rx="6" />
    <text class="hp-word hp-word-strong" x="47" y="34">{{ a }}</text>
    <rect class="hp-solid" x="14" y="48" width="66" height="20" rx="4" />
    <HelpLabel :x="47" :y="62" text="WIDE2-2" />
    <path class="hp-dim" :d="arrow(92, 30, 130, 30)" />
    <path class="hp-bad" d="M134 20v20" />
    <rect class="hp-frame" x="138" y="16" width="90" height="28" rx="8" />
    <text class="hp-word hp-word-strong" x="183" y="34">{{ t("settings.pair.explain.you") }}</text>
  </svg>
</template>
