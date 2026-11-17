<script setup lang="ts">
// The slider of one of a sound card's own levels, 0 to 100 percent (the radio's `radio/<id>/tx_card` or `rx_card`, the key given): the Transmit level row has it where the card has a playback control
// (components/HfLevelRow.vue), the Receive level row beside its bar where the card has a capture control (components/LevelBar.vue's slot). It stands where the card is (`level`, the radio's row: what the card
// says, before the operator ever touched it), the thumb follows the pointer while it is dragged, and the value is saved when it is let go (or at each step of the keys); from the save until the row says the
// card's level again the thumb stays where it was let go. A drag ends when the pointer is let go, or the slider loses the focus, as well as at the save: a thumb let go where it was pressed saves nothing,
// and follows the card again. The daemon sets the card at once and restarts nothing. Its width is its own, so that nothing beside it moves; with no `level` (the card has no such control, or its levels are
// not known yet) it is that room alone, empty, so that the bar beside it keeps its width and place when the slider comes. The slot is given the percent shown (the Transmit level row says it beside the slider).
import { computed, ref, watch } from "vue";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";

const props = defineProps<{ id?: string; label: string; settingKey: string; level: number | null; form: SettingsFormState }>();
const { connection } = useDaemonContext();
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
  <input
    v-if="level !== null"
    :id="id"
    class="cardslider"
    type="range"
    min="0"
    max="100"
    step="1"
    :value="shown"
    :aria-label="label"
    :aria-valuetext="t('settings.cardlevel.value', { value: shown })"
    @input="follow"
    @change="save"
    @pointerup="end"
    @pointercancel="end"
    @blur="end"
  />
  <span v-else class="cardslider" aria-hidden="true"></span>
  <slot v-if="level !== null" :value="shown" />
</template>

<style scoped>
.cardslider {
  flex: 1 1 0;
  min-width: 60px;
  height: 20px; /* the height of the (i) beside it: the row is as high with the slider as without */
  margin: 0;
  accent-color: var(--accent);
}
</style>
