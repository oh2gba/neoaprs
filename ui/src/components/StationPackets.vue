<script setup lang="ts">
// The packets of one station heard in each of the last 24 hours, as bars on its card (components/StationCard.vue): the statistics card's graph (components/StatsCard.vue), for the station alone. The daemon is asked
// (`packet_history` with the call; the card emits `ask` and components/StationCards.vue sends it) when the card opens and every minute after, as the running hour grows. Until the answer comes the graph is its empty frame
// over the same hours, so the card does not grow when the bars arrive.
import { computed, onMounted, watch } from "vue";
import TrendChart from "@/components/TrendChart.vue";
import { t } from "@/i18n";
import { emptyHistory, historyPoints } from "@/lib/stats";
import type { PacketHistoryMessage } from "@/protocol/protocol";

const props = defineProps<{
  /** the latest answer for this station; null until one came */
  history: PacketHistoryMessage | null;
  now: number;
}>();
const emit = defineEmits<{ ask: [] }>();

const shown = computed(() => (props.history === null ? emptyHistory(props.now) : historyPoints(props.history)));

onMounted(() => emit("ask"));
watch(
  () => Math.floor(props.now / 60_000),
  () => emit("ask"),
);
</script>

<template>
  <div class="station-packets" data-packets>
    <TrendChart
      :title="t('stats.chart')"
      :unit="t('stats.chart_unit')"
      :from="shown.from"
      :to="shown.to"
      :main="shown.points"
      as-bars
      zero
      tone="packets"
      :value-decimals="0"
    />
  </div>
</template>
