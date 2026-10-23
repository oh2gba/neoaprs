<script setup lang="ts">
// The station cards over the map. On a tablet and a desktop they are a row at the left of the map, side by side, the oldest at the left and the newest at the right, each the whole card, as it is alone (with several weather stations open each is the full weather card
// with its graphs, and the graphs are on the same value axes in every card, so that the stations can be compared). A card has its own cross. Two or more cards have **Close all** over the map's top left, beside the zoom buttons, and **Message these 3** beside it when two or
// more of the cards are for stations that can be messaged (one text to all of them, in the group compose of the Messages tab). How many there may be is the page's (composables/useSelection.ts), and a row that is wider than the map has room for closes
// its oldest card (`overflow`): a card is never made narrower. On a phone the one card is a bottom sheet that is part of the screen: folded to its head and the first facts, it opens up with a tap or a swipe up on its grip, folds with a swipe down, and a
// swipe down on the folded sheet closes it; its cross is there too.
import { computed, nextTick, onMounted, ref, watch } from "vue";
import StationCard from "@/components/StationCard.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useResized } from "@/composables/useResized";
import { provideWxSpan } from "@/composables/useWxSpan";
import { CARDS_FREE_SIDE, CARD_GAP, type SizeClass } from "@/lib/layout";
import { SWIPE_MIN, sheetMove, type SheetMove } from "@/lib/sheet";
import { isWeatherStation, sharedRanges } from "@/lib/weather";
import type { StationRow } from "@/protocol/protocol";

const props = defineProps<{
  rows: readonly StationRow[];
  size: SizeClass;
}>();
const { now, aging, weatherSeries } = useDaemonContext();
// (Forget, Message, Edit, ... are the card's own events: they go on)
const emit = defineEmits<{
  close: [call: string];
  closeAll: [];
  messageAll: [calls: string[]];
  forget: [call: string];
  edit: [name: string];
  kill: [name: string];
  message: [call: string];
  timeout: [call: string, minutes: number];
  clearTimeout: [call: string];
  weather: [call: string, hours: number];
  overflow: [];
}>();

/** The stations of the open cards that a message can go to: stations, not ourselves, and not one the daemon says cannot be messaged (the email gateway, an object...). */
const askable = computed(() => props.rows.filter((row) => row.kind === "station" && row.can_message && !row.is_me && !row.own).map((row) => row.call));

// the weather graphs of all the open cards are of one span; and while two or more weather stations are open they are on the same value axes too, so that their curves can be compared (one card has its own)
const span = provideWxSpan();
const ranges = computed(() => {
  const weather = props.rows.filter(isWeatherStation);
  return weather.length < 2
    ? undefined
    : sharedRanges(
        weather.map((row) => weatherSeries.value.get(row.call) ?? null),
        Number(span.value),
      );
});

// a row that is wider than the map has room for is not squeezed: the oldest card closes (the page does that when it hears `overflow`)
const stack = ref<HTMLElement | null>(null);
function fit(): void {
  const el = stack.value;
  if (!el || props.size === "phone" || props.rows.length < 2) return;
  const room = el.clientWidth - CARDS_FREE_SIDE; // (0 where nothing is laid out: no room to measure against)
  const cards = [...el.children] as HTMLElement[];
  const total = cards.reduce((sum, card) => sum + card.offsetWidth, 0) + CARD_GAP * (cards.length - 1);
  if (el.clientWidth > 0 && total > room) emit("overflow");
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
  <div v-if="rows.length > 1 && size !== 'phone'" class="cards-actions">
    <button type="button" class="btn small cards-closeall" @click="emit('closeAll')">Close all</button>
    <button v-if="askable.length > 1" type="button" class="btn small cards-message" @click="emit('messageAll', askable)">
      Message these {{ askable.length }}
    </button>
  </div>
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
    <StationCard
      v-for="row in rows"
      :key="row.call"
      :row="row"
      :now="now"
      :aging="aging"
      :weather-series="weatherSeries.get(row.call) ?? null"
      :ranges="ranges"
      @close="emit('close', row.call)"
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
