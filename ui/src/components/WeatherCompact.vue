<script setup lang="ts">
// The weather of a weather station on a compact card, the card of one of several that are open (several weather stations are opened to be compared, so the graphs are the point): the latest readings in one line (temperature, wind with its gusts, humidity,
// pressure) with how long ago they were heard, and under them a small graph for each quantity the station sends: temperature, wind with its gusts, pressure, humidity and rain, two side by side, 44 px high, the hours under the last row. The graphs are of the span that all the open
// cards share (composables/useWxSpan.ts), and when the cards share value axes too (`ranges`: lib/weather.ts `sharedRanges`) the curves of the stations can be read against each other. The daemon is asked for the series when the card opens and when a new
// observation comes (`ask`), as the whole card does.
import { computed, watch } from "vue";
import TrendChart from "@/components/TrendChart.vue";
import { useWxSpan } from "@/composables/useWxSpan";
import type { Point } from "@/lib/chart";
import { ageText, bearingText, dateTimeText } from "@/lib/format";
import { arrowAngle, columnOf, hasValues, humidityText, pressureText, tempText, windSpeedText, type Ranges } from "@/lib/weather";
import type { StationRow, WeatherSeriesMessage } from "@/protocol/protocol";

const props = defineProps<{ row: StationRow; series: WeatherSeriesMessage | null; now: number; ranges?: Ranges }>();
const emit = defineEmits<{ ask: [call: string, hours: number] }>();

const span = useWxSpan();
const hours = computed(() => Number(span.value));
watch(
  () => [props.row.call, hours.value, props.row.weather_at] as const,
  ([call, asked]) => emit("ask", call, asked),
  { immediate: true },
);

const wx = computed(() => props.row.weather);
const angle = computed(() => arrowAngle(wx.value?.wind_dir ?? null));
const mine = computed(() => (props.series !== null && props.series.call === props.row.call && props.series.hours === hours.value ? props.series : null));
const to = computed(() => Math.floor(props.now / 60_000) * 60_000);
const from = computed(() => to.value - hours.value * 3_600_000);
const columns = computed(() => ({
  temp: columnOf(mine.value, "temp"),
  wind: columnOf(mine.value, "wind"),
  gust: columnOf(mine.value, "gust"),
  pressure: columnOf(mine.value, "pressure"),
  humidity: columnOf(mine.value, "humidity"),
  rain: columnOf(mine.value, "rain"),
}));
interface Graph {
  key: string;
  title: string;
  unit: string;
  main: Point[];
  band?: Point[];
  asBars?: boolean;
  zero?: boolean;
  tone: "temp" | "wind" | "pressure" | "humidity" | "rain";
  range?: readonly [number, number];
}
/** The graphs this station has, in the order they are drawn. */
const graphs = computed(() => {
  const all: Graph[] = [
    { key: "temp", title: "Temperature", unit: "°C", main: columns.value.temp, tone: "temp", range: props.ranges?.temp },
    {
      key: "wind",
      title: "Wind",
      unit: "km/h",
      main: columns.value.wind,
      band: columns.value.gust,
      zero: true,
      tone: "wind",
      range: props.ranges?.wind,
    },
    { key: "pressure", title: "Pressure", unit: "hPa", main: columns.value.pressure, tone: "pressure", range: props.ranges?.pressure },
    { key: "humidity", title: "Humidity", unit: "%", main: columns.value.humidity, tone: "humidity", range: props.ranges?.humidity },
    { key: "rain", title: "Rain 1 h", unit: "mm", main: columns.value.rain, asBars: true, zero: true, tone: "rain", range: props.ranges?.rain },
  ];
  return all.filter((g) => hasValues(g.main));
});
/** "6 km/h SW (13)": the speed, the direction it comes from, the gusts. */
const windLine = computed(() => {
  const w = props.row.weather;
  if (w === null) return "";
  const dir = w.wind_dir === null ? "" : ` ${bearingText(w.wind_dir).replace(/^\d+° /, "")}`;
  const gust = w.gust_kmh === null ? "" : ` (${windSpeedText(w.gust_kmh).replace(" km/h", "")})`;
  return `${windSpeedText(w.wind_kmh)}${dir}${gust}`;
});
const heard = computed(() => (props.row.weather_at === null ? "" : `${ageText(props.row.weather_at, props.now)} ago`));
</script>

<template>
  <section class="wx wx-compact" aria-label="Weather">
    <div v-if="wx" class="wx-line">
      <span class="wx-temp" title="Temperature">{{ tempText(wx.temp_c) }}</span>
      <span class="wx-wind" title="Wind">
        <svg v-if="angle !== null" class="wx-arrow" viewBox="-12 -12 24 24" aria-hidden="true">
          <g :transform="`rotate(${angle})`"><path d="M0,-10 L6,6 L0,3 L-6,6 Z" /></g>
        </svg>
        {{ windLine }}
      </span>
      <span v-if="wx.humidity !== null" title="Humidity">{{ humidityText(wx.humidity) }}</span>
      <span v-if="wx.pressure_hpa !== null" title="Pressure">{{ pressureText(wx.pressure_hpa) }}</span>
      <span class="wx-when muted" :title="dateTimeText(row.weather_at)">{{ heard }}</span>
    </div>
    <div v-else class="wx-none muted">No weather report heard yet.</div>
    <p v-if="wx && mine === null" class="wx-none muted">Loading the observations…</p>
    <div v-if="graphs.length > 0" class="wx-graphs">
      <TrendChart
        v-for="(g, i) in graphs"
        :key="g.key"
        :title="g.title"
        :unit="g.unit"
        :from="from"
        :to="to"
        :main="g.main"
        :band="g.band"
        :as-bars="g.asBars"
        :zero="g.zero"
        :tone="g.tone"
        :range="g.range"
        compact
        :time-labels="i >= graphs.length - (graphs.length % 2 === 0 ? 2 : 1)"
      />
    </div>
  </section>
</template>
