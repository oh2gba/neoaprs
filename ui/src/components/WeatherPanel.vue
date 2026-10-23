<script setup lang="ts">
// The weather of a weather station at the top of its card: the latest readings (temperature large, the wind as an arrow with its speed and gusts, humidity, pressure, rain over the hour, 24 hours and since midnight,
// luminosity and snow when they are sent) with how long ago they were heard, and under them the trend graphs of the last 24 hours or the last 7 days (the switch is remembered): temperature, pressure, wind with its
// gusts as a lighter band, and rain as bars. The daemon is asked for the series when the card opens, when the switch changes and when a new observation comes (`ask`). With several weather cards open `ranges` is the value axes they share (lib/weather.ts `sharedRanges`): each graph is on the axis it is given.
import { computed, watch } from "vue";
import TrendChart from "@/components/TrendChart.vue";
import { useWxSpan } from "@/composables/useWxSpan";
import { t } from "@/i18n";
import { agoWords, bearingText, dateTimeText } from "@/lib/format";
import { arrowAngle, columnOf, hasValues, humidityText, pressureText, rainText, tempText, windSpeedText, type Ranges } from "@/lib/weather";
import type { StationRow, WeatherSeriesMessage } from "@/protocol/protocol";

const props = defineProps<{ row: StationRow; series: WeatherSeriesMessage | null; now: number; ranges?: Ranges }>();
const emit = defineEmits<{ ask: [call: string, hours: number] }>();

/** The spans of the graphs, with the words of each in the page's language. */
const spans = computed(() => [
  { hours: "24" as const, label: t("time.span.h", { n: 24 }) },
  { hours: "168" as const, label: t("weather.span.days", { n: 7 }) },
]);
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
const heard = computed(() => (props.row.weather_at === null ? "" : agoWords(props.row.weather_at, props.now)));
/** "from 123° ESE gusts 20 km/h": the direction the wind comes from and its gusts, as far as they are known. */
const windNote = computed(() => {
  const w = wx.value;
  if (w === null) return "";
  return [
    w.wind_dir === null ? "" : t("weather.wind_from", { bearing: bearingText(w.wind_dir) }),
    w.gust_kmh === null ? "" : t("weather.gusts", { speed: windSpeedText(w.gust_kmh) }),
  ]
    .filter((part) => part !== "")
    .join(" ");
});
</script>

<template>
  <section class="wx" :aria-label="t('weather.label')">
    <div v-if="wx" class="wx-now">
      <div class="wx-temp" :title="t('weather.temperature')">{{ tempText(wx.temp_c) }}</div>
      <div class="wx-wind" :title="t('weather.wind')">
        <svg v-if="angle !== null" class="wx-arrow" viewBox="-12 -12 24 24" aria-hidden="true">
          <g :transform="`rotate(${angle})`"><path d="M0,-10 L6,6 L0,3 L-6,6 Z" /></g>
        </svg>
        <span v-else class="wx-arrow" aria-hidden="true" />
        <div>
          <div class="wx-big">{{ windSpeedText(wx.wind_kmh) }}</div>
          <div class="muted">{{ windNote }}</div>
        </div>
      </div>
      <dl class="wx-values">
        <dt>{{ t("weather.humidity") }}</dt>
        <dd>{{ humidityText(wx.humidity) }}</dd>
        <dt>{{ t("weather.pressure") }}</dt>
        <dd>{{ pressureText(wx.pressure_hpa) }}</dd>
        <dt>{{ t("weather.rain_1h") }}</dt>
        <dd>{{ rainText(wx.rain_1h_mm) }}</dd>
        <dt>{{ t("weather.rain_24h") }}</dt>
        <dd>{{ rainText(wx.rain_24h_mm) }}</dd>
        <dt>{{ t("weather.rain_today") }}</dt>
        <dd>{{ rainText(wx.rain_today_mm) }}</dd>
        <template v-if="wx.luminosity !== null">
          <dt>{{ t("weather.light") }}</dt>
          <dd>{{ wx.luminosity }} W/m²</dd>
        </template>
        <template v-if="wx.snow_mm !== null">
          <dt>{{ t("weather.snow_24h") }}</dt>
          <dd>{{ rainText(wx.snow_mm) }}</dd>
        </template>
      </dl>
      <div class="wx-when muted" :title="dateTimeText(row.weather_at)">{{ heard }}</div>
    </div>
    <div v-else class="wx-none muted">{{ t("weather.none") }}</div>
    <div class="wx-span" role="group" :aria-label="t('weather.period')">
      <button
        v-for="s in spans"
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
    <p v-if="mine === null" class="wx-none muted">{{ t("weather.loading") }}</p>
    <p v-else-if="mine.points.length === 0" class="wx-none muted">{{ t("weather.no_observations") }}</p>
    <template v-else>
      <TrendChart
        v-if="hasValues(charts.temp)"
        :title="t('weather.temperature')"
        unit="°C"
        :from="from"
        :to="to"
        :main="charts.temp"
        tone="temp"
        :range="ranges?.temp"
      />
      <TrendChart
        v-if="hasValues(charts.pressure)"
        :title="t('weather.pressure')"
        unit="hPa"
        :from="from"
        :to="to"
        :main="charts.pressure"
        tone="pressure"
        :range="ranges?.pressure"
      />
      <TrendChart
        v-if="hasValues(charts.wind)"
        :title="t('weather.chart.wind')"
        unit="km/h"
        :from="from"
        :to="to"
        :main="charts.wind"
        :band="charts.gust"
        zero
        tone="wind"
        :range="ranges?.wind"
      />
      <TrendChart
        v-if="hasValues(charts.rain)"
        :title="t('weather.chart.rain')"
        unit="mm"
        :from="from"
        :to="to"
        :main="charts.rain"
        as-bars
        zero
        tone="rain"
        :range="ranges?.rain"
      />
    </template>
  </section>
</template>
