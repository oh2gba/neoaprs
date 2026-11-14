<script setup lang="ts">
// The signal of a station's packets over the last day, as a line on its card (components/StationCard.vue), in the pattern of the speed graph (components/StationSpeed.vue): the SNR of each packet heard direct from it (the RSSI where the radio gives that and not the SNR), from the readings
// the daemon has (`signal_series`; the card emits `ask` and components/StationCards.vue sends it) when the card opens and whenever a new reading of the station comes. The card shows it only for a station whose latest reading
// (`signal_at` of the row) is in the last day, from the row, so that the room is kept before the answer comes and nothing moves when it does: the graph is its empty frame until then, and stays that frame for a station
// with fewer than two readings in the day.
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
