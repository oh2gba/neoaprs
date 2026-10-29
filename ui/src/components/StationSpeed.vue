<script setup lang="ts">
// The speed of a moving station over its trip (its track as the map draws it, from the oldest point to now: lib/speed.ts, `tripStart`), as a line on its card (components/StationCard.vue), from the speeds of its positions the daemon has (`speed_series`; the card emits `ask` and
// components/StationCards.vue sends it) when the card opens and whenever a new position of the station comes. The card shows it only for a station that moves (lib/speed.ts, `isMoving`, from the row, so that a
// fixed station's card has no room kept for it); until the answer comes the graph is its empty frame over the same span, so the card does not grow when the line arrives.
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
    <TrendChart :title="t('station.speed_chart')" unit="km/h" :from="shown.from" :to="shown.to" :main="shown.points" zero tone="speed" :value-decimals="0" />
  </div>
</template>
