<script setup lang="ts">
// The station cards over the map. On a tablet and a desktop they are a column at the left of the map, the newest on top (the first card stays where it is when another is added above it), each with its own cross, and a "Close all" over
// them when there is more than one; with more than one card each is compact (components/StationCard.vue), and its "More" makes it the only one, whole. How many there may be is the page's (composables/useSelection.ts). On a phone the one card is a bottom
// sheet that is part of the screen: folded to its head and the first facts, it opens up with a tap or a swipe up on its grip, folds with a swipe down, and a swipe down on the folded sheet closes it; its cross is there too.
import { ref, watch } from "vue";
import StationCard from "@/components/StationCard.vue";
import type { Aging } from "@/lib/aging";
import type { SizeClass } from "@/lib/layout";
import { SWIPE_MIN, sheetMove, type SheetMove } from "@/lib/sheet";
import type { StationRow, WeatherSeriesMessage } from "@/protocol/protocol";

const props = defineProps<{ rows: readonly StationRow[]; size: SizeClass; now: number; aging: Aging; weatherSeries: WeatherSeriesMessage | null }>();
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
}>();

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
  <div v-if="rows.length > 0" class="cardstack" :class="{ sheet: size === 'phone', expanded }">
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
      :weather-series="weatherSeries"
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
