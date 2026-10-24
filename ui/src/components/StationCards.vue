<script setup lang="ts">
// The station cards over the map. On a tablet and a desktop they are a row at the left of the map, side by side, the oldest at the left and the newest at the right, each the whole card, as it is alone (with several weather stations open each is the full weather card
// with its graphs, and the graphs are on the same value axes in every card, so that the stations can be compared). A card has its own cross. Two or more cards have **Close all** over the map's top left, beside the zoom buttons, and **Message these 3** beside it when two or
// more of the cards are for stations that can be messaged (one text to all of them, in the group compose of the Messages tab). How many there may be is the page's (composables/useSelection.ts), and a row that is wider than the map has room for closes
// its oldest card (`overflow`): a card is never made narrower. On a tablet and a desktop a card can be dragged by its head, or moved with Alt and the arrows (composables/useCardDrag.ts) anywhere over the map, and it keeps its place while it is open (`places`, the page's, for the session). Moving a card
// never moves another: the first time one is moved every open card is pinned where it stands (the moved card leaves its slot empty), a card that closes leaves the others where they are, and a card that is opened goes to the first free slot of the row, never on top of a card. On a phone the one card is a bottom sheet that is part of the screen: folded to its head and the first facts, it opens up with a tap or a swipe up on its grip, folds with a swipe down, and a
// swipe down on the folded sheet closes it; its cross is there too.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import MessageGlyph from "@/components/MessageGlyph.vue";
import StationCard from "@/components/StationCard.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useCardDrag, type Places } from "@/composables/useCardDrag";
import { useResized } from "@/composables/useResized";
import { provideWxSpan } from "@/composables/useWxSpan";
import { t } from "@/i18n";
import { type Place } from "@/lib/cardmove";
import { CARDS_FREE_SIDE, CARD_GAP, type SizeClass } from "@/lib/layout";
import { SWIPE_MIN, sheetMove, type SheetMove } from "@/lib/sheet";
import { canMessage } from "@/lib/stations";
import { isWeatherStation, sharedRanges } from "@/lib/weather";
import type { StationRow } from "@/protocol/protocol";

const props = defineProps<{
  rows: readonly StationRow[];
  size: SizeClass;
  /** The calls of the pinned cards (a tablet and a desktop): they stay open past Esc and Close all, and keep their places. */
  pinned?: readonly string[];
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
  pin: [call: string, on: boolean];
  weather: [call: string, hours: number];
  overflow: [];
}>();

/** The stations of the open cards that a message can go to: stations, not ourselves, and not one the daemon says cannot be messaged (the email gateway, an object...). */
const askable = computed(() => props.rows.filter(canMessage).map((row) => row.call));

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
// (a card that was moved is out of the row: it takes no room in it)
const stack = ref<HTMLElement | null>(null);
function fit(): void {
  const el = stack.value;
  if (!el || props.size === "phone") return;
  const cards = [...el.querySelectorAll<HTMLElement>(":scope > .card:not(.moved)")];
  if (cards.length < 2) return;
  const room = el.clientWidth - CARDS_FREE_SIDE; // (0 where nothing is laid out: no room to measure against)
  const total = cards.reduce((sum, card) => sum + card.offsetWidth, 0) + CARD_GAP * (cards.length - 1);
  if (el.clientWidth > 0 && total > room) emit("overflow");
}

// Where the cards that were moved stand (a tablet and a desktop only; the page keeps it, for the session, and uses it for how many cards the row holds: composables/useStationCards.ts). A card that is closed forgets its place.
const places = defineModel<Places>("places", { default: () => ({}) });
const movable = computed(() => props.size !== "phone");
const placeOf = (call: string): Place | undefined => (movable.value ? places.value[call] : undefined);
const placeStyle = (place: Place | undefined) => (place ? { left: `${place.x}px`, top: `${place.y}px` } : undefined);
const drag = useCardDrag(stack, places, () => movable.value);
const isPinned = (call: string): boolean => props.pinned?.includes(call) ?? false;
/** A card is pinned where it stands (it gets its place first, so that the cards around it never move it), or its pin is taken away (it stays where it is). */
function pin(call: string): void {
  const on = !isPinned(call);
  if (on) drag.pinHere(call);
  emit("pin", call, on);
}
function resized(): void {
  drag.keepInside();
  fit();
}
useResized(stack, resized);
// Cards come and go and the others stay where they are: the cards behind one that closes are pinned where they stand (before the page is drawn without it), and a card that is opened is put in the first free slot (once it is in the page, before it is drawn)
const callsOf = (): string[] => props.rows.map((row) => row.call);
watch(callsOf, (calls, before) => {
  const gone = before.filter((call) => !calls.includes(call));
  if (gone.length === 0) return;
  // (one write: what the page is told is seen only when it has been drawn again)
  const kept = Object.entries({ ...places.value, ...drag.pinAfter(gone, calls) }).filter(([call]) => calls.includes(call));
  const next = Object.fromEntries(kept);
  if (kept.length !== Object.keys(places.value).length || kept.some(([call, at]) => places.value[call] !== at)) places.value = next;
});
// A card that stands where it was put grows downwards (its Details, the graphs of a weather station): when it would leave the map it is kept inside it
let sizes: ResizeObserver | null = null;
function watchSizes(): void {
  sizes?.disconnect();
  sizes = null;
  if (typeof ResizeObserver !== "function" || !stack.value) return;
  const observer = new ResizeObserver(() => drag.keepInside());
  for (const card of stack.value.querySelectorAll(":scope > .card")) observer.observe(card);
  sizes = observer;
}
watch(
  callsOf,
  (calls, before) => {
    drag.placeNew(calls.filter((one) => !before.includes(one)));
    watchSizes();
  },
  { flush: "post" },
);
onMounted(watchSizes);
onBeforeUnmount(() => sizes?.disconnect());
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
    <button v-if="rows.some((row) => !isPinned(row.call))" type="button" class="btn cards-closeall" @click="emit('closeAll')">
      {{ t("station.cards.close_all") }}
    </button>
    <button v-if="askable.length > 1" type="button" class="btn msgbtn cards-message" @click="emit('messageAll', askable)">
      <MessageGlyph :size="14" /> {{ t("station.cards.message_all", { n: askable.length }) }}
    </button>
  </div>
  <div
    v-if="rows.length > 0"
    ref="stack"
    class="cardstack"
    :class="{ sheet: size === 'phone', expanded }"
    @pointerdown="drag.down"
    @pointermove="drag.move"
    @pointerup="drag.up"
    @pointercancel="drag.up"
    @keydown="drag.key"
  >
    <button
      v-if="size === 'phone'"
      type="button"
      class="sheet-grip"
      :aria-expanded="expanded"
      :aria-label="expanded ? t('station.cards.fold') : t('station.cards.open')"
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
      :data-call="row.call"
      :class="{ moved: placeOf(row.call) !== undefined }"
      :style="placeStyle(placeOf(row.call))"
      :movable="movable"
      :pinned="isPinned(row.call)"
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
      @pin="pin(row.call)"
      @weather="(call, hours) => emit('weather', call, hours)"
    />
  </div>
</template>
