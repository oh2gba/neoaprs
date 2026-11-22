<script setup lang="ts">
// The slider for one of a sound card's levels, 0 to 100 percent, with its percent beside it
// (`radio/<id>/tx_card` or `rx_card`; used by HfLevelRow.vue and LevelBar.vue). It shows
// `level`, the card's own value; while dragging the thumb follows the pointer and the value is
// saved on release or at each key step, and the thumb stays put until the row reports the card's
// level again. Its width is a share of the row's control column, the same in both rows and kept
// without `level`, so the bar beside it does not move; in a narrow column both are `narrow`. It
// is drawn here so that it looks the same in every web engine.
import { computed, onMounted, ref, watch } from "vue";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useElementWidth } from "@/composables/useElementWidth";
import { t } from "@/i18n";

const props = defineProps<{
  id?: string;
  label: string;
  settingKey: string;
  level: number | null;
  form: SettingsFormState;
}>();
const { connection } = useDaemonContext();
/** The narrowest control column that fits the slider beside the Receive level's bar: 40 % of it
 * leaves a track of about 70 px after the bar, number, (i) and gaps. */
const NARROW_BELOW = 300;
const room = ref<HTMLElement | null>(null);
const column = ref<HTMLElement | null>(null);
onMounted(() => {
  column.value = room.value?.parentElement ?? null;
});
const columnWidth = useElementWidth(column);
const narrow = computed(() => columnWidth.value > 0 && columnWidth.value < NARROW_BELOW);
/** The operator's thumb position until the row reports the card's level again; null: the card's
 * own. */
const put = ref<number | null>(null);
/** Whether the thumb is being dragged: a level reported meanwhile does not move it. */
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
/** The drag ended without a save (released where pressed): the thumb follows the card again. */
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
/* The slider's width: the same share of the control column in both level rows, never more than
   what the Receive level's bar (60 px), number (9ch), (i) (20 px) and gaps leave. */
.cardslider {
  display: flex;
  flex: 0 0 min(40%, calc(100% - 104px - 9ch));
  font-family: var(--mono);
  align-items: center;
  gap: 8px;
  min-width: 0;
  height: 20px; /* as high as the (i) beside it */
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
/* Chromium and WebKit: the track carries the accent up to the thumb itself */
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
