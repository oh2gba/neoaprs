<script setup lang="ts">
// Speed of a moving station over its trip (lib/speed.ts `tripStart`), as a line on its card.
// The card emits `ask` (`speed_series`) when it opens and on each new position, and shows this
// only for a moving station (`isMoving`), so fixed stations' cards reserve no room. Until the
// answer arrives the graph is an empty frame over the same span.
import { computed, onMounted, watch } from "vue";
import TrendChart from "@/components/TrendChart.vue";
import { t } from "@/i18n";
import { speedPoints } from "@/lib/speed";
import type { SpeedSeriesMessage } from "@/protocol/protocol";

const props = defineProps<{
  /** when the station's latest position came: a new one asks again */
  positionAt: string | null;
  /** the latest answer for this station; null until one came */
  series: SpeedSeriesMessage | null;
  /** when the trip began (ms): the graph's left edge */
  from: number;
  now: number;
}>();
const emit = defineEmits<{ ask: [] }>();

const shown = computed(() => speedPoints(props.series, props.from, props.now));

onMounted(() => emit("ask"));
watch(
  () => props.positionAt,
  () => emit("ask"),
);
</script>

<template>
  <div class="station-speed" data-speed>
    <TrendChart
      :title="t('station.speed_chart')"
      unit="km/h"
      :from="shown.from"
      :to="shown.to"
      :main="shown.points"
      zero
      tone="speed"
      :value-decimals="0"
    />
  </div>
</template>
