<script setup lang="ts">
// The bar of the map's replay: play and pause, the slider over the span, the clock (ReplayTime),
// the speed and the span, and a cross that closes it (as does Esc). Speed and span can be changed
// only while paused. Nothing in it moves while the clock runs: the clock has tabular figures in a
// fixed-width box and the play button keeps one size.
import { computed } from "vue";
import IconButton from "@/components/IconButton.vue";
import ReplayTime from "@/components/ReplayTime.vue";
import type { Replay } from "@/composables/useReplay";
import { t } from "@/i18n";
import { REPLAY_SPANS, REPLAY_SPEEDS, spanLabel } from "@/lib/replay";

const props = defineProps<{ replay: Replay }>();
const emit = defineEmits<{ close: [] }>();

const data = computed(() => props.replay.data.value);
const playing = computed(() => props.replay.playing.value);
const speeds = computed(() => REPLAY_SPEEDS.map((n) => ({ value: n, label: t("map.replay.speed_n", { n }) })));
const spans = computed(() => REPLAY_SPANS.map((hours) => ({ value: hours, label: spanLabel(hours) })));
/** The title of a choice: what it is, and while playing that it can be changed when paused. */
const titleOf = (what: string): string => (playing.value ? t("map.replay.when_paused", { what }) : what);
const speedTitle = computed(() => titleOf(t("map.replay.speed")));
const spanTitle = computed(() => titleOf(t("map.replay.span")));

function setSpeed(event: Event): void {
  props.replay.pace(Number((event.target as HTMLSelectElement).value));
}

function setSpan(event: Event): void {
  props.replay.ask(Number((event.target as HTMLSelectElement).value));
}

/** Esc closes the replay, also from the slider; an open select list takes its Esc first. */
function onKey(event: KeyboardEvent): void {
  if (event.key !== "Escape" || event.defaultPrevented || (event.target as HTMLElement).tagName === "SELECT") return;
  event.preventDefault();
  emit("close");
}
</script>

<template>
  <div class="replaybar" role="group" :aria-label="t('map.replay.label')" :aria-busy="replay.loading.value" @keydown="onKey">
    <button
      class="btn replay-play"
      type="button"
      :disabled="!data"
      :aria-label="t(playing ? 'map.replay.pause' : 'map.replay.play')"
      :title="t(playing ? 'map.replay.pause' : 'map.replay.play')"
      @click="replay.toggle()"
    >
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
        <path v-if="playing" d="M3 2h3v10H3zM8 2h3v10H8z" fill="currentColor" />
        <path v-else d="M3 1.5v11l9-5.5z" fill="currentColor" />
      </svg>
    </button>
    <ReplayTime :replay="replay" />
    <select
      class="input replay-speed"
      :value="replay.speed.value"
      :disabled="playing"
      :aria-label="t('map.replay.speed')"
      :title="speedTitle"
      @change="setSpeed"
    >
      <option v-for="o in speeds" :key="o.value" :value="o.value">{{ o.label }}</option>
    </select>
    <select class="input replay-span" :value="replay.hours.value" :disabled="playing" :aria-label="t('map.replay.span')" :title="spanTitle" @change="setSpan">
      <option v-for="o in spans" :key="o.value" :value="o.value">{{ o.label }}</option>
    </select>
    <IconButton kind="close" class="replay-close" :label="t('map.replay.close')" @click="emit('close')" />
  </div>
</template>
