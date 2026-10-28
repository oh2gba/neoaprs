<script setup lang="ts">
// The bar of the map's replay (composables/useReplay.ts is its clock, composables/useMapReplay.ts what the map draws): play and pause, the slider over the span, which seeks, the time of the replay as a clock, the
// speed and the span (the hours of the Stations tab's On map for), and the cross, which closes the replay (and so does Esc, with the station cards: composables/useAppShell.ts). It stands at the bottom of the map in
// the middle, clear of the station cards and the statistics card, which rise above it while it is open (styles/map.css); on a phone it is the width of the map less a 16 px margin each side, and the slider has a line
// of its own. Nothing in it moves as the clock runs or a choice changes: the clock is of tabular figures in a box of a fixed width, the play button is one size whatever it shows, the choices are selects.
import { computed } from "vue";
import IconButton from "@/components/IconButton.vue";
import type { Replay } from "@/composables/useReplay";
import { t } from "@/i18n";
import { STATION_HOURS } from "@/lib/aging";
import { CLOCK_NONE, REPLAY_SPEEDS, replayClock } from "@/lib/replay";

const props = defineProps<{ replay: Replay }>();
const emit = defineEmits<{ close: [] }>();
const MINUTE = 60_000;

const data = computed(() => props.replay.data.value);
const clock = computed(() => (data.value ? replayClock(props.replay.at.value, data.value.start, data.value.end) : CLOCK_NONE));
const playing = computed(() => props.replay.playing.value);

function seek(event: Event): void {
  props.replay.seek(Number((event.target as HTMLInputElement).value));
}

function setSpeed(event: Event): void {
  props.replay.pace(Number((event.target as HTMLSelectElement).value));
}

/** Esc in the bar closes the replay, the slider's too (the station cards leave an Esc in a field to the field); a select's own list takes its Esc first. */
function onKey(event: KeyboardEvent): void {
  if (event.key !== "Escape" || event.defaultPrevented || (event.target as HTMLElement).tagName === "SELECT") return;
  event.preventDefault();
  emit("close");
}

function setSpan(event: Event): void {
  props.replay.ask(Number((event.target as HTMLSelectElement).value));
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
    <input
      class="replay-slider"
      type="range"
      :min="data?.start ?? 0"
      :max="data?.end ?? 1"
      :step="MINUTE"
      :value="data ? replay.at.value : 0"
      :disabled="!data"
      :aria-label="t('map.replay.time')"
      :aria-valuetext="clock"
      @input="seek"
    />
    <output class="replay-clock" :title="t('map.replay.time')">{{ clock }}</output>
    <select class="input replay-speed" :value="replay.speed.value" :aria-label="t('map.replay.speed')" :title="t('map.replay.speed')" @change="setSpeed">
      <option v-for="n in REPLAY_SPEEDS" :key="n" :value="n">{{ t("map.replay.speed_n", { n }) }}</option>
    </select>
    <select class="input replay-span" :value="replay.hours.value" :aria-label="t('map.replay.span')" :title="t('map.replay.span')" @change="setSpan">
      <option v-for="n in STATION_HOURS" :key="n" :value="n">{{ t("station.table.hours", { n }) }}</option>
    </select>
    <IconButton kind="close" class="replay-close" :label="t('map.replay.close')" @click="emit('close')" />
  </div>
</template>
