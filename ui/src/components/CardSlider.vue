<script setup lang="ts">
// The slider of one of a sound card's own levels, 0 to 100 percent (the radio's `radio/<id>/tx_card` or `rx_card`, the key given), with the percent it stands at beside it: the Transmit level row has it where the card
// has a playback control (components/HfLevelRow.vue), the Receive level row before its bar where the card has a capture control (components/LevelBar.vue's slot). It stands where the card is (`level`, the radio's row:
// what the card says, before the operator ever touched it), the thumb follows the pointer while it is dragged, and the value is saved when it is let go (or at each step of the keys); from the save until the row says
// the card's level again the thumb stays where it was let go. A drag ends when the pointer is let go, or the slider loses the focus, as well as at the save: a thumb let go where it was pressed saves nothing, and follows
// the card again. The daemon sets the card at once and restarts nothing. Its room is a share of the row's control column, the same in both rows, so that the two sliders start, run and end alike, and the percent has a
// room of its own that every value fits; with no `level` (the card has no such control, or its levels are not known yet) the room is there, empty, so that the bar beside it keeps its width and place when the slider
// comes. Where the control column is too narrow for a slider of a useful length beside the Receive level's bar, its number and the (i) (the panel of a window under 1280 px, a tablet's), both sliders are
// `narrow`: each has the column's line but the room of the (i), the Receive level's under its bar, as on a phone (styles/responsive.css); both rows see the same column, so both decide alike. The slider is drawn here (a thin track, the part up to the thumb in the accent colour, a round thumb with the border of the page's buttons), so that it looks the same in every web engine the app uses.
import { computed, onMounted, ref, watch } from "vue";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useElementWidth } from "@/composables/useElementWidth";
import { t } from "@/i18n";

const props = defineProps<{ id?: string; label: string; settingKey: string; level: number | null; form: SettingsFormState }>();
const { connection } = useDaemonContext();
/** The narrowest control column that has the slider beside the Receive level's bar: there 40 % of it is what the bar (60 px at least), its number (9ch), the (i) (20 px) and their gaps leave, a track of
 * about 70 px; a narrower one has the sliders on lines of their own. */
const NARROW_BELOW = 300;
const room = ref<HTMLElement | null>(null);
const column = ref<HTMLElement | null>(null);
onMounted(() => {
  column.value = room.value?.parentElement ?? null;
});
const columnWidth = useElementWidth(column);
const narrow = computed(() => columnWidth.value > 0 && columnWidth.value < NARROW_BELOW);
/** Where the operator put the thumb, until the row says the card's level again; null: the card's own. */
const put = ref<number | null>(null);
/** Whether the thumb is being dragged: a level the row says meanwhile does not take it from under the pointer. */
let dragging = false;
watch(
  () => props.level,
  () => {
    if (!dragging) put.value = null;
  },
);
watch(connection, (state) => {
  if (state !== "open") put.value = null;
});

const shown = computed(() => put.value ?? props.level ?? 0);
const valueOf = (event: Event): number => Number((event.target as HTMLInputElement).value);
function follow(event: Event): void {
  dragging = true;
  put.value = valueOf(event);
}
/** The drag is over without a save (let go where it was pressed: no change event): the thumb follows the card again where it stands at the card's level. */
function end(): void {
  if (!dragging) return;
  dragging = false;
  if (put.value === props.level) put.value = null;
}
function save(event: Event): void {
  dragging = false;
  const value = valueOf(event);
  put.value = value === props.level ? null : value;
  props.form.choose({ [props.settingKey]: String(value) });
}
</script>

<template>
  <span ref="room" class="cardslider" :class="{ narrow }" :aria-hidden="level === null ? 'true' : undefined">
    <template v-if="level !== null">
      <input
        :id="id"
        class="cardslider-input"
        type="range"
        min="0"
        max="100"
        step="1"
        :value="shown"
        :style="{ '--fill': `${shown}%` }"
        :aria-label="label"
        :aria-valuetext="t('settings.cardlevel.value', { value: shown })"
        @input="follow"
        @change="save"
        @pointerup="end"
        @pointercancel="end"
        @blur="end"
      />
      <output class="mono cardslider-value">{{ t("settings.cardlevel.value", { value: shown }) }}</output>
    </template>
  </span>
</template>

<style scoped>
/* the slider's room: the same share of the control column in the Transmit and the Receive level rows, empty or not, and never more than the Receive level's bar (60 px at least), its number (9ch of the
   same type), the (i) (20 px) and the three gaps leave it */
.cardslider {
  display: flex;
  flex: 0 0 min(40%, calc(100% - 104px - 9ch));
  font-family: var(--mono);
  align-items: center;
  gap: 8px;
  min-width: 0;
  height: 20px; /* the height of the (i) beside it: the row is as high with the slider as without */
}
.cardslider-value {
  flex: none;
  width: 5ch; /* "100 %" and "7 %" take the same room */
  text-align: right;
  white-space: nowrap;
}
.cardslider-input {
  --fill: 0%;
  flex: 1 1 0;
  min-width: 0;
  height: 20px;
  margin: 0;
  padding: 0;
  appearance: none;
  -webkit-appearance: none;
  background: transparent;
  cursor: pointer;
}
.cardslider-input:focus-visible {
  outline: none; /* the ring is the thumb's */
}
.cardslider-input:disabled {
  opacity: 0.5;
  cursor: default;
}
/* Chromium (Edge WebView2, Qt WebEngine) and WebKit (WebKitGTK): the track carries the accent up to the thumb itself */
.cardslider-input::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: var(--radius-pill);
  background: linear-gradient(to right, var(--accent) var(--fill), var(--border) var(--fill));
}
.cardslider-input::-webkit-slider-thumb {
  box-sizing: border-box;
  width: 16px;
  height: 16px;
  margin-top: -6px; /* the thumb's middle on the track's */
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--panel);
  appearance: none;
  -webkit-appearance: none;
}
.cardslider-input:not(:disabled):hover::-webkit-slider-thumb {
  border-color: var(--accent);
}
.cardslider-input:focus-visible::-webkit-slider-thumb {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}
/* Firefox: the track, and the part up to the thumb */
.cardslider-input::-moz-range-track {
  height: 4px;
  border-radius: var(--radius-pill);
  background: var(--border);
}
.cardslider-input::-moz-range-progress {
  height: 4px;
  border-radius: var(--radius-pill);
  background: var(--accent);
}
.cardslider-input::-moz-range-thumb {
  box-sizing: border-box;
  width: 16px;
  height: 16px;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--panel);
}
.cardslider-input:not(:disabled):hover::-moz-range-thumb {
  border-color: var(--accent);
}
.cardslider-input:focus-visible::-moz-range-thumb {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}
</style>
