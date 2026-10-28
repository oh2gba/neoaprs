<script setup lang="ts">
// The part of the replay's bar (components/ReplayBar.vue) that moves with the clock: the slider over the span, which seeks, and the time of the replay as a clock. They are a component of their own so that
// the clock's ten steps a second draw these two and nothing else: the rest of the bar is drawn again only when a choice, play or pause or the span changes. (Drawn with the clock, the bar's selects were patched
// at each step, Vue writing the `value` of each select and of each of its options again, and the browser redrew them: they flickered while the replay played.) Two elements and no box of their own, so that
// the bar lays them out as before, the slider on a line of its own where the bar is narrow.
import { computed } from "vue";
import type { Replay } from "@/composables/useReplay";
import { t } from "@/i18n";
import { CLOCK_NONE, replayClock } from "@/lib/replay";

const props = defineProps<{ replay: Replay }>();
const MINUTE = 60_000;

const data = computed(() => props.replay.data.value);
const clock = computed(() => (data.value ? replayClock(props.replay.at.value, data.value.start, data.value.end) : CLOCK_NONE));

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
