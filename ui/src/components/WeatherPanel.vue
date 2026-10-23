<script setup lang="ts">
// The weather of a weather station at the top of its card: the latest readings (temperature large, the wind as an arrow with its speed and gusts, humidity, pressure, rain over the hour, 24 hours and since midnight,
// luminosity and snow when they are sent) with how long ago they were heard, and under them the trend graphs of the last 24 hours or the last 7 days (the switch is remembered): temperature, pressure, wind with its
// gusts as a lighter band, and rain as bars. The daemon is asked for the series when the card opens, when the switch changes and when a new observation comes (`ask`). The compact form of a card that is one of several is components/WeatherCompact.vue.
import { computed, watch } from "vue";
import TrendChart from "@/components/TrendChart.vue";
import { useWxSpan } from "@/composables/useWxSpan";
import { ageText, bearingText, dateTimeText } from "@/lib/format";
import { arrowAngle, columnOf, hasValues, humidityText, pressureText, rainText, tempText, windSpeedText } from "@/lib/weather";
import type { StationRow, WeatherSeriesMessage } from "@/protocol/protocol";

const props = defineProps<{ row: StationRow; series: WeatherSeriesMessage | null; now: number }>();
const emit = defineEmits<{ ask: [call: string, hours: number] }>();

const SPANS = [
  { hours: "24", label: "24 h" },
  { hours: "168", label: "7 days" },
] as const;
const span = useWxSpan(); // (the one of all the open cards, when there are several)
const hours = computed(() => Number(span.value));

watch(
  () => [props.row.call, hours.value, props.row.weather_at] as const,
  ([call, asked]) => emit("ask", call, asked),
  { immediate: true },
);

const wx = computed(() => props.row.weather);
const angle = computed(() => arrowAngle(wx.value?.wind_dir ?? null));
// the series the card asked for (an answer for another station or span is not shown), drawn up to the minute
const mine = computed(() => (props.series !== null && props.series.call === props.row.call && props.series.hours === hours.value ? props.series : null));
const to = computed(() => Math.floor(props.now / 60_000) * 60_000);
const from = computed(() => to.value - hours.value * 3_600_000);
const charts = computed(() => ({
  temp: columnOf(mine.value, "temp"),
  pressure: columnOf(mine.value, "pressure"),
  wind: columnOf(mine.value, "wind"),
  gust: columnOf(mine.value, "gust"),
  rain: columnOf(mine.value, "rain"),
}));
const heard = computed(() => (props.row.weather_at === null ? "" : `${ageText(props.row.weather_at, props.now)} ago`));
</script>

<template>
  <section class="wx" aria-label="Weather">
    <div v-if="wx" class="wx-now">
      <div class="wx-temp" title="Temperature">{{ tempText(wx.temp_c) }}</div>
      <div class="wx-wind" title="Wind">
        <svg v-if="angle !== null" class="wx-arrow" viewBox="-12 -12 24 24" aria-hidden="true">
          <g :transform="`rotate(${angle})`"><path d="M0,-10 L6,6 L0,3 L-6,6 Z" /></g>
        </svg>
        <span v-else class="wx-arrow" aria-hidden="true" />
        <div>
          <div class="wx-big">{{ windSpeedText(wx.wind_kmh) }}</div>
          <div class="muted">
            <template v-if="wx.wind_dir !== null">from {{ bearingText(wx.wind_dir) }}</template>
            <template v-if="wx.gust_kmh !== null"> gusts {{ windSpeedText(wx.gust_kmh) }}</template>
          </div>
        </div>
      </div>
      <dl class="wx-values">
        <dt>Humidity</dt>
        <dd>{{ humidityText(wx.humidity) }}</dd>
        <dt>Pressure</dt>
        <dd>{{ pressureText(wx.pressure_hpa) }}</dd>
        <dt>Rain 1 h</dt>
        <dd>{{ rainText(wx.rain_1h_mm) }}</dd>
        <dt>Rain 24 h</dt>
        <dd>{{ rainText(wx.rain_24h_mm) }}</dd>
        <dt>Rain today</dt>
        <dd>{{ rainText(wx.rain_today_mm) }}</dd>
        <template v-if="wx.luminosity !== null">
          <dt>Light</dt>
          <dd>{{ wx.luminosity }} W/m²</dd>
        </template>
        <template v-if="wx.snow_mm !== null">
          <dt>Snow 24 h</dt>
          <dd>{{ rainText(wx.snow_mm) }}</dd>
        </template>
      </dl>
      <div class="wx-when muted" :title="dateTimeText(row.weather_at)">{{ heard }}</div>
    </div>
    <div v-else class="wx-none muted">No weather report heard yet.</div>
    <div class="wx-span" role="group" aria-label="Period of the graphs">
      <button
        v-for="s in SPANS"
        :key="s.hours"
        type="button"
        class="btn small"
        :class="{ primary: span === s.hours }"
        :aria-pressed="span === s.hours"
        @click="span = s.hours"
      >
        {{ s.label }}
      </button>
    </div>
    <p v-if="mine === null" class="wx-none muted">Loading the observations…</p>
    <p v-else-if="mine.points.length === 0" class="wx-none muted">No observations in this period.</p>
    <template v-else>
      <TrendChart v-if="hasValues(charts.temp)" title="Temperature" unit="°C" :from="from" :to="to" :main="charts.temp" tone="temp" />
      <TrendChart v-if="hasValues(charts.pressure)" title="Pressure" unit="hPa" :from="from" :to="to" :main="charts.pressure" tone="pressure" />
      <TrendChart
        v-if="hasValues(charts.wind)"
        title="Wind and gusts"
        unit="km/h"
        :from="from"
        :to="to"
        :main="charts.wind"
        :band="charts.gust"
        zero
        tone="wind"
      />
      <TrendChart v-if="hasValues(charts.rain)" title="Rain, last hour" unit="mm" :from="from" :to="to" :main="charts.rain" as-bars zero tone="rain" />
    </template>
  </section>
</template>
