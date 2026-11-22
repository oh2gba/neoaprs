<script setup lang="ts">
// The part of the replay bar that follows the clock: the seeking slider and the clock text. It is a
// separate component so that the clock's steps redraw only these two; redrawing the bar's selects
// at each step made them flicker. It has no box of its own so the bar can lay the two out.
import { computed } from "vue";
import type { Replay } from "@/composables/useReplay";
import { t } from "@/i18n";
import { CLOCK_NONE, replayClock } from "@/lib/replay";

const props = defineProps<{ replay: Replay }>();
const MINUTE = 60_000;

const data = computed(() => props.replay.data.value);
const clock = computed(() =>
  data.value ? replayClock(props.replay.at.value, data.value.start, data.value.end) : CLOCK_NONE,
);

function seek(event: Event): void {
  props.replay.seek(Number((event.target as HTMLInputElement).value));
}
</script>

<template>
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
</template>
