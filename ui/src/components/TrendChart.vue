<script setup lang="ts">
// One trend graph as inline SVG in the page's colours, used by the weather card, the packet
// statistics, and the speed and signal graphs: a smooth line through the readings that carries
// across gaps, with an optional lighter band up to the gusts, bars (rain), or stacked bars (the
// packets of each radio); labelled ticks on both axes; and a heading with the value and time
// of the observation under the pointer (the latest one when there is none), so nothing moves.
// Scaling and paths are in lib/chart.ts. A series with no value draws only the frame. `range`
// is the value axis shared by several weather cards, rounded to round numbers.
import { computed, ref } from "vue";
import { formatNumber, t } from "@/i18n";
import {
  bandPath,
  bars,
  extent,
  stackedBars,
  lastIndex,
  linePath,
  linearScale,
  nearestIndex,
  niceTicks,
  tickDecimals,
  timeTicks,
  usualGap,
  type Point,
} from "@/lib/chart";
import { clockText } from "@/lib/format";

const props = withDefaults(
  defineProps<{
    title: string;
    unit: string;
    /** the time axis, ms since 1970 */
    from: number;
    to: number;
    /** the observations, oldest first */
    main: readonly Point[];
    /** the upper edge of a band that is drawn between `main` and it (the gusts) */
    band?: readonly Point[];
    /** the series is drawn as bars (rain) */
    asBars?: boolean;
    /** with `asBars`, the stacked parts of each bar, bottom first, each with a tone class
     * (sets `--tone`); `main` is their sum */
    parts?: readonly { key: string; tone: string; points: readonly Point[] }[];
    /** the value axis includes 0 (wind, rain) */
    zero?: boolean;
    tone: "temp" | "pressure" | "wind" | "rain" | "packets" | "speed" | "signal";
    /** the decimals of the value in the heading (1 for a weather reading; 0 for a count) */
    valueDecimals?: number;
    /** the lowest and the highest value of the axis, from the cards that share it */
    range?: readonly [number, number];
    /** how a value is written in the heading and on the axis (the locale's number by default) */
    numberText?: (value: number, decimals: number) => string;
  }>(),
  { band: () => [], asBars: false, parts: () => [], zero: false, range: undefined, valueDecimals: 1, numberText: formatNumber },
);

const W = 320;
const H = 100;
const LEFT = 36;
const RIGHT = W - 6;
const TOP = 6;
const BOTTOM = H - 18;

const hover = ref<number | null>(null);

const values = computed(() => [...props.main, ...props.band].flatMap((p) => (p.v === null ? [] : [p.v])));
const axis = computed(() => {
  const [lo, hi] = props.range ?? extent(values.value, props.zero);
  return niceTicks(lo, hi, 4);
});
const x = computed(() => linearScale([props.from, props.to], [LEFT, RIGHT]));
const y = computed(() => linearScale([axis.value.min, axis.value.max], [BOTTOM, TOP]));
const decimals = computed(() => tickDecimals(axis.value.step));
const xTicks = computed(() => timeTicks(props.from, props.to).map((t) => ({ ...t, x: x.value(t.at) })));
const yTicks = computed(() => axis.value.ticks.map((v) => ({ v, y: y.value(v), label: props.numberText(v, decimals.value) })));

const line = computed(() => (props.asBars ? "" : linePath(props.main, x.value, y.value)));
const upper = computed(() => linePath(props.band, x.value, y.value));
const area = computed(() => bandPath(props.main, props.band, x.value, y.value));
const barWidth = computed(() => {
  const span = Math.max(1, props.to - props.from);
  return Math.min(8, Math.max(1.5, (usualGap(props.main) * 0.8 * (RIGHT - LEFT)) / span));
});
const columns = computed(() => (props.asBars && props.parts.length === 0 ? bars(props.main, x.value, y.value, 0, barWidth.value) : []));
const stacked = computed(() => (props.asBars ? stackedBars(props.parts, x.value, y.value, barWidth.value) : []));

const shown = computed(() => {
  const i = hover.value ?? lastIndex(props.main);
  const p = props.main[i];
  return p === undefined || p.v === null ? null : { p, at: x.value(p.t), top: y.value(p.v), hovered: hover.value !== null };
});
const readout = computed(() =>
  shown.value === null
    ? ""
    : `${props.numberText(shown.value.p.v ?? 0, props.valueDecimals)} ${props.unit}  ${clockText(new Date(shown.value.p.t).toISOString())}`,
);

function move(event: PointerEvent): void {
  const svg = event.currentTarget as SVGSVGElement;
  const box = svg.getBoundingClientRect();
  const place = box.width > 0 ? ((event.clientX - box.left) / box.width) * W : W;
  const t = props.from + ((place - LEFT) / (RIGHT - LEFT)) * (props.to - props.from);
  const i = nearestIndex(props.main, t);
  hover.value = i < 0 ? null : i;
}
</script>

<template>
  <figure class="trend" :class="`tone-${tone}`">
    <figcaption class="trend-head">
      <span>{{ title }}</span>
      <span class="trend-read mono">{{ readout }}</span>
    </figcaption>
    <svg
      class="trend-svg"
      :viewBox="`0 0 ${W} ${H}`"
      role="img"
      :aria-label="t('weather.chart.label', { title, unit })"
      @pointermove="move"
      @pointerdown="move"
      @pointerleave="hover = null"
    >
      <g class="trend-grid">
        <g v-for="tick in yTicks" :key="`y${tick.v}`">
          <line :x1="LEFT" :x2="RIGHT" :y1="tick.y" :y2="tick.y" />
          <text :x="LEFT - 4" :y="tick.y + 3" text-anchor="end">{{ tick.label }}</text>
        </g>
        <g v-for="tick in xTicks" :key="`x${tick.at}`">
          <line class="tick" :x1="tick.x" :x2="tick.x" :y1="BOTTOM" :y2="BOTTOM + 3" />
          <text :x="tick.x" :y="H - 4" text-anchor="middle">{{ tick.label }}</text>
        </g>
      </g>
      <path v-if="area" class="trend-band" :d="area" />
      <path v-if="upper" class="trend-upper" :d="upper" />
      <path v-if="line" class="trend-line" :d="line" />
      <rect v-for="(b, i) in columns" :key="i" class="trend-bar" :x="b.x" :y="b.y" :width="b.width" :height="b.height" />
      <rect v-for="(b, i) in stacked" :key="`s${i}`" class="trend-bar" :class="b.tone" :x="b.x" :y="b.y" :width="b.width" :height="b.height" />
      <g v-if="shown && shown.hovered">
        <line class="trend-cursor" :x1="shown.at" :x2="shown.at" :y1="TOP" :y2="BOTTOM" />
        <circle class="trend-dot" :cx="shown.at" :cy="shown.top" r="3" />
      </g>
    </svg>
  </figure>
</template>
