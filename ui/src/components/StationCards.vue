<script setup lang="ts">
// The station cards over the map. On a tablet and a desktop they are a column at the left of the map, the newest on top (the first card stays where it is when another is added above it), each with its own cross, and a "Close all" over
// them when there is more than one; with more than one card each is compact (components/StationCard.vue), and its "More" makes it the only one, whole. How many there may be is the page's (composables/useSelection.ts). On a phone the one card is a bottom
// sheet that is part of the screen: folded to its head and the first facts, it opens up with a tap or a swipe up on its grip, folds with a swipe down, and a swipe down on the folded sheet closes it; its cross is there too.
import { computed, nextTick, onMounted, ref, watch } from "vue";
import StationCard from "@/components/StationCard.vue";
import { useResized } from "@/composables/useResized";
import { provideWxSpan } from "@/composables/useWxSpan";
import type { Aging } from "@/lib/aging";
import { CARDS_FREE, CARD_GAP, type SizeClass } from "@/lib/layout";
import { SWIPE_MIN, sheetMove, type SheetMove } from "@/lib/sheet";
import { isWeatherStation, sharedRanges } from "@/lib/weather";
import type { StationRow, WeatherSeriesMessage } from "@/protocol/protocol";

const props = defineProps<{
  rows: readonly StationRow[];
  size: SizeClass;
  now: number;
  aging: Aging;
  weatherSeries: ReadonlyMap<string, WeatherSeriesMessage>;
}>();
// (Forget, Message, Edit, ... are the card's own events: they go on)
const emit = defineEmits<{
  close: [call: string];
  closeAll: [];
  only: [call: string];
  forget: [call: string];
  edit: [name: string];
  kill: [name: string];
  message: [call: string];
  timeout: [call: string, minutes: number];
  clearTimeout: [call: string];
  weather: [call: string, hours: number];
  overflow: [];
}>();

// the weather graphs of all the open cards are of one span; and while two or more weather stations are open they are on the same value axes too, so that their curves can be compared (one card has its own)
const span = provideWxSpan();
const ranges = computed(() => {
  const weather = props.rows.filter(isWeatherStation);
  return weather.length < 2
    ? undefined
    : sharedRanges(
        weather.map((row) => props.weatherSeries.get(row.call) ?? null),
        Number(span.value),
      );
});

// a column that is taller than the map has room for (weather cards with graphs are tall) is not squeezed: the oldest card closes (the page does that when it hears `overflow`)
const stack = ref<HTMLElement | null>(null);
function fit(): void {
  const el = stack.value;
  if (!el || props.size === "phone" || props.rows.length < 2) return;
  const map = el.parentElement?.clientHeight ?? 0; // (0 where nothing is laid out: no room to measure against)
  const kids = [...el.children] as HTMLElement[]; // (the cards and Close all, and the gaps between them; the box of the column itself is cut at its largest height, so it cannot say)
  const total = kids.reduce((sum, kid) => sum + kid.offsetHeight, 0) + CARD_GAP * (kids.length - 1);
  if (map > 0 && total > map - CARDS_FREE) emit("overflow");
}
useResized(stack, fit);
watch(
  () => props.rows.length,
  () => void nextTick(fit),
);
onMounted(() => void nextTick(fit));

const expanded = ref(false);
const newest = (): string | undefined => props.rows.at(-1)?.call;
// a card of another station starts folded
watch(newest, () => (expanded.value = false));

function apply(move: SheetMove): void {
  const call = newest();
  if (move === "close" && call !== undefined) emit("close", call);
  else expanded.value = move === "toggle" ? !expanded.value : move === "expand";
}

let startY: number | null = null;
let swiped = false;
function down(event: PointerEvent): void {
  startY = event.clientY;
  swiped = false;
  (event.currentTarget as HTMLElement | null)?.setPointerCapture?.(event.pointerId);
}
function up(event: PointerEvent): void {
  if (startY === null) return;
  const dy = event.clientY - startY;
  startY = null;
  if (Math.abs(dy) < SWIPE_MIN) return;
  swiped = true;
  apply(sheetMove(dy, expanded.value));
}
function cancel(): void {
  startY = null;
}
/** A tap, or the Enter of the keyboard (a swipe has done its work already). */
function tap(): void {
  if (swiped) swiped = false;
  else apply("toggle");
}
</script>

<template>
  <div v-if="rows.length > 0" ref="stack" class="cardstack" :class="{ sheet: size === 'phone', expanded }">
    <button
      v-if="size === 'phone'"
      type="button"
      class="sheet-grip"
      :aria-expanded="expanded"
      :aria-label="expanded ? 'Fold the card' : 'Open the card'"
      @pointerdown="down"
      @pointerup="up"
      @pointercancel="cancel"
      @click="tap"
    >
      <span aria-hidden="true"></span>
    </button>
    <button v-else-if="rows.length > 1" type="button" class="btn small cards-closeall" @click="emit('closeAll')">Close all</button>
    <StationCard
      v-for="row in rows"
      :key="row.call"
      :row="row"
      :now="now"
      :aging="aging"
      :weather-series="weatherSeries.get(row.call) ?? null"
      :ranges="ranges"
      :compact="rows.length > 1"
      @close="emit('close', row.call)"
      @only="emit('only', $event)"
      @forget="emit('forget', $event)"
      @edit="emit('edit', $event)"
      @kill="emit('kill', $event)"
      @message="emit('message', $event)"
      @timeout="(call, minutes) => emit('timeout', call, minutes)"
      @clear-timeout="emit('clearTimeout', $event)"
      @weather="(call, hours) => emit('weather', call, hours)"
    />
  </div>
</template>
