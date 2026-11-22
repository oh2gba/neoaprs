<script setup lang="ts">
// Packets heard from one station in each of the last 24 hours, as bars on its card. The card
// emits `ask` (`packet_history`) when it opens and every minute. Until the answer arrives the
// graph is an empty frame over the same hours, so the card does not grow.
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
