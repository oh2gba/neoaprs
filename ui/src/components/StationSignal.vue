<script setup lang="ts">
// Line graph of a station's signal over the last day on its card: the SNR of each packet heard
// direct (the RSSI when the radio gives no SNR). The card emits `ask` (`signal_series`) when it
// opens and on each new reading. It shows the graph only when the row's `signal_at` is within
// the last day, so room is reserved before the answer; with fewer than two readings the graph
// stays an empty frame.
import { computed, onMounted, watch } from "vue";
import TrendChart from "@/components/TrendChart.vue";
import { t } from "@/i18n";
import { HOUR_MS } from "@/lib/format";
import { SIGNAL_HOURS, signalLine, signalNumber } from "@/lib/signal";
import type { SignalSeriesMessage } from "@/protocol/protocol";

const props = defineProps<{
  /** when the station's latest reading came: a new one asks again */
  signalAt: string | null;
  /** the latest answer for this station; null until one came */
  series: SignalSeriesMessage | null;
  /** what the station's latest reading measured: the graph's kind until the answer has a line */
  measured: "snr" | "rssi";
  now: number;
}>();
const emit = defineEmits<{ ask: [] }>();

const from = computed(() => props.now - SIGNAL_HOURS * HOUR_MS);
const line = computed(() => signalLine(props.series, from.value));
const kind = computed(() => line.value?.kind ?? props.measured);

onMounted(() => emit("ask"));
watch(
  () => props.signalAt,
  () => emit("ask"),
);
</script>

<template>
  <div class="station-signal" data-signal>
    <TrendChart
      :title="t(kind === 'snr' ? 'station.signal_chart_snr' : 'station.signal_chart_rssi')"
      :unit="kind === 'snr' ? 'dB' : 'dBm'"
      :from="from"
      :to="now"
      :main="line?.points ?? []"
      tone="signal"
      :value-decimals="0"
      :number-text="signalNumber"
    />
  </div>
</template>
