<script setup lang="ts">
// The Transmit level of an HF radio, a row under Tune: the modem's audio gain in whole dB
// (`radio/<id>/tx_gain_db`), lowered and raised by two buttons, each press saved at once, with
// the latest transmission's peak in dBFS beside it (orange at 0 or over, where the sound card
// clips). Where the sound card has a playback level (`card.tx`) and the gain is 0, the slider
// (CardSlider.vue, `tx_card`) replaces the buttons; a non-zero gain keeps the buttons and the
// daemon leaves the card's level alone. A gain that was non-zero keeps the buttons until the row
// is seen again (useWhenShown.ts `useInView`), so the row does not change shape under the
// pointer. Until the card's levels are known (`card.read`) the row keeps its room hidden.
import CardSlider from "@/components/CardSlider.vue";
import InfoTip from "@/components/InfoTip.vue";
import { computed, ref, watch } from "vue";
import type { Settings } from "@/composables/useSettings";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { useInView } from "@/composables/useWhenShown";
import { t } from "@/i18n";
import { clips, dbText, gainText } from "@/lib/hflevel";
import { typeOf, type PageRadio } from "@/lib/radios";

const props = defineProps<{
  id: string;
  settings: Settings;
  form: SettingsFormState;
  radio: PageRadio;
  settingKey: string;
}>();
/** The gain range from the radio type's field (none: the level is not moved). */
const range = computed(() => typeOf(props.radio)?.fields.find((field) => field.key === "tx_gain_db")?.range ?? [0, 0]);
const min = computed(() => range.value[0]);
const max = computed(() => range.value[1]);
/** The modem whose gain this is: the radio's own row. */
const modem = computed(() => props.radio.row.modem);

const gain = computed(() => {
  const stored = Number.parseInt(props.settings.draft[props.settingKey] ?? "", 10);
  return Number.isFinite(stored) ? stored : (modem.value?.tx_gain_db ?? 0);
});
const peak = computed(() => modem.value?.tx_peak_dbfs ?? null);
/** Whether the gain was non-zero while in sight: the buttons stay until the row is out of sight. */
const stepped = ref(gain.value !== 0);
watch(gain, (value) => {
  if (value !== 0) stepped.value = true;
});
const row = ref<HTMLElement | null>(null);
const inView = useInView(row);
watch(inView, (shown) => {
  if (!shown) stepped.value = gain.value !== 0;
});
/** Whether the card's levels are known; until then neither slider nor buttons are drawn. */
const known = computed(() => props.radio.row.card.read);
/** The card's playback level, for the slider, where it has one and the gain is the card's. */
const card = computed(() => (stepped.value ? null : props.radio.row.card.tx));
const cardKey = computed(() => `radio/${props.radio.id}/tx_card`);
/** Whether the modem reports the peak of what it sends (the HF modem does; Direwolf does not). */
const peakShown = computed(() => props.radio.row.can.scope);

function move(by: number): void {
  const next = Math.max(min.value, Math.min(max.value, gain.value + by));
  if (next !== gain.value) props.form.choose({ [props.settingKey]: String(next) });
}
</script>

<template>
  <div
    ref="row"
    class="field txlevel"
    :class="{ 'field-room': !known }"
    :aria-hidden="known ? undefined : 'true'"
    :inert="!known || undefined"
  >
    <label :for="`${id}-up`">{{ t("settings.txlevel.label") }}</label>
    <div class="field-control txlevel-control">
      <template v-if="known">
        <CardSlider
          v-if="card !== null"
          :id="`${id}-up`"
          :label="t('settings.txlevel.label')"
          :setting-key="cardKey"
          :level="card"
          :form="form"
        />
        <template v-else>
          <button
            class="btn stepbtn"
            type="button"
            :disabled="gain <= min"
            :title="t('settings.txlevel.lower')"
            :aria-label="t('settings.txlevel.lower')"
            @click="move(-1)"
          >
            −
          </button>
          <output class="mono txlevel-value">{{ t("settings.txlevel.value", { value: gainText(gain) }) }}</output>
          <button
            :id="`${id}-up`"
            class="btn stepbtn"
            type="button"
            :disabled="gain >= max"
            :title="t('settings.txlevel.raise')"
            :aria-label="t('settings.txlevel.raise')"
            @click="move(1)"
          >
            +
          </button>
        </template>
        <InfoTip :label="t('settings.txlevel.tip_label')"
          ><span class="info-line">{{ t(card !== null ? "settings.txlevel.card_tip1" : "settings.txlevel.tip1") }}</span
          ><span v-if="peakShown" class="info-line">{{ t("settings.txlevel.tip2") }}</span></InfoTip
        >
      </template>
    </div>
    <output v-if="peakShown" class="mono txlevel-peak" :class="{ clip: clips(peak) }">{{
      t("settings.txlevel.peak", { value: dbText(peak) })
    }}</output>
  </div>
</template>

<style scoped>
.txlevel-control {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: var(--control-h); /* as high with the slider, the buttons or neither */
}
/* the two steps are small buttons, not the width of an action button */
.field-control > .btn.stepbtn:first-child,
.btn.stepbtn {
  min-width: 0;
  width: var(--control-h);
}
.txlevel-control > .infotip {
  margin-left: auto;
}
.txlevel-value {
  min-width: 6ch;
  white-space: nowrap;
  text-align: center;
}
/* the peak sits under the control, in its column, and keeps its line */
.txlevel-peak {
  grid-column: 2;
  min-height: 1.4em;
  white-space: nowrap;
  color: var(--muted);
}
.txlevel-peak.clip {
  color: var(--bad);
  font-weight: 600;
}
</style>
