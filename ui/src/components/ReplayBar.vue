<script setup lang="ts">
// The bar of the map's replay (composables/useReplay.ts is its clock, composables/useMapReplay.ts what the map draws): play and pause, the slider over the span and the clock (components/ReplayTime.vue, the
// only part drawn at each step of the clock), the speed and the span (the hours of the Stations tab's On map for, then 2, 3 and 7 days), and the cross, which closes the replay (and so does Esc, with the
// station cards: composables/useAppShell.ts). The speed and the span are chosen while the replay is paused or at its end: while it plays they are off, their title saying so, and keep their size. It stands at
// the bottom of the map in the middle, clear of the station cards and the statistics card, which rise above it while it is open (styles/map.css); on a phone it is the width of the map less a 16 px margin each
// side, and the slider has a line of its own. Nothing in it moves as the clock runs or a choice changes: the clock is of tabular figures in a box of a fixed width, the play button is one size whatever it
// shows, the choices are selects, and their options are made once (again only when the language changes).
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
/** The title of a choice: what it is, and while the replay plays that it is chosen when paused. */
const titleOf = (what: string): string => (playing.value ? t("map.replay.when_paused", { what }) : what);
const speedTitle = computed(() => titleOf(t("map.replay.speed")));
const spanTitle = computed(() => titleOf(t("map.replay.span")));

function setSpeed(event: Event): void {
  props.replay.pace(Number((event.target as HTMLSelectElement).value));
}

function setSpan(event: Event): void {
  props.replay.ask(Number((event.target as HTMLSelectElement).value));
}

/** Esc in the bar closes the replay, the slider's too (the station cards leave an Esc in a field to the field); a select's own list takes its Esc first. */
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
