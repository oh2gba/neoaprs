<script setup lang="ts">
// The Transmit level of an HF radio, a row under Tune: the gain the modem sends its audio to the radio with, in whole dB (the radio's setting `radio/<id>/tx_gain_db`, the key given), lowered and raised by the two buttons, each press saved at once. The modem takes it while it runs, and
// the tune tone follows it, so the operator presses Tune and watches the radio's ALC while the level moves. Beside it the peak of the latest transmission in dBFS (the modem's own reading), which turns orange at 0 or over, where the sound card clips.
// The room of the number is kept, so that nothing moves when it changes. The range is the field's of the radio's type, the modem the radio's row. A modem that says no peak (a Sound card radio's Direwolf: `can.scope` is the modem giving its audio) has the row without it.
// Where the radio's sound card has a playback level of its own (the row's `card.tx`) and the modem's gain is at its start (0), the row has the card's slider in the place of the two buttons (components/CardSlider.vue,
// the radio's `tx_card`), and the modem's gain is not offered: one transmit level, the card's, which is set without a restart; the percent stands beside it in the room of the dB. A gain that is not 0 keeps the
// two buttons, and the daemon then leaves the card's playback level as it is: nothing changes the level out of sight. The row keeps its shape while it is in sight: a gain that was not 0 when the row came
// into sight, or since, keeps the buttons when + or - reaches 0 under the pointer; the slider comes the next time the row is seen (its fold or tab opened again, composables/useWhenShown.ts `useInView`).
// Until the card's levels are known (`card.read`) the row has neither, at its height.
import CardSlider from "@/components/CardSlider.vue";
import InfoTip from "@/components/InfoTip.vue";
import { computed, ref, watch } from "vue";
import type { Settings } from "@/composables/useSettings";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { useInView } from "@/composables/useWhenShown";
import { t } from "@/i18n";
import { clips, dbText, gainText } from "@/lib/hflevel";
import { typeOf, type PageRadio } from "@/lib/radios";

const props = defineProps<{ id: string; settings: Settings; form: SettingsFormState; radio: PageRadio; settingKey: string }>();
/** The range of the gain: the field's of the radio's type (none: the level is not moved). */
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
/** Whether the gain was not 0 while the row was in sight: it keeps the two buttons until the row is out of sight. */
const stepped = ref(gain.value !== 0);
watch(gain, (value) => {
  if (value !== 0) stepped.value = true;
});
const row = ref<HTMLElement | null>(null);
const inView = useInView(row);
watch(inView, (shown) => {
  if (!shown) stepped.value = gain.value !== 0;
});
/** Whether the card's levels are known: until then the row draws neither the slider nor the buttons. */
const known = computed(() => props.radio.row.card.read);
/** The card's own playback level, where it has one and the gain is the card's: the slider's. */
const card = computed(() => (stepped.value ? null : props.radio.row.card.tx));
const cardKey = computed(() => `radio/${props.radio.id}/tx_card`);
/** Whether the modem says the peak of what it sends: one that gives its audio (the HF modem, whose scope and peak come the same way); a Sound card radio's Direwolf gives none. */
const peakShown = computed(() => props.radio.row.can.scope);

function move(by: number): void {
  const next = Math.max(min.value, Math.min(max.value, gain.value + by));
  if (next !== gain.value) props.form.choose({ [props.settingKey]: String(next) });
}
</script>

<template>
  <div ref="row" class="field txlevel">
    <label :for="`${id}-up`">{{ t("settings.txlevel.label") }}</label>
    <div class="field-control txlevel-control">
      <template v-if="known">
        <CardSlider
          v-if="card !== null"
          :id="`${id}-up`"
          v-slot="{ value }"
          :label="t('settings.txlevel.label')"
          :setting-key="cardKey"
          :level="card"
          :form="form"
          ><output class="mono txlevel-value">{{ t("settings.cardlevel.value", { value }) }}</output></CardSlider
        >
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
    <output v-if="peakShown" class="mono txlevel-peak" :class="{ clip: clips(peak) }">{{ t("settings.txlevel.peak", { value: dbText(peak) }) }}</output>
  </div>
</template>

<style scoped>
.txlevel-control {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: var(--control-h); /* the row is as high with the card's slider as with the two buttons, and with neither */
}
/* the two steps are small buttons, not the width of an action button that the first button of a row has */
.field-control > .btn.stepbtn:first-child,
.btn.stepbtn {
  min-width: 0;
  width: var(--control-h);
}
.txlevel-value {
  min-width: 6ch;
  text-align: center;
}
/* the peak stands under the control, in its column, and keeps its line whatever it says */
.txlevel-peak {
  grid-column: 2;
  min-height: 1.4em;
  color: var(--muted);
}
.txlevel-peak.clip {
  color: var(--bad);
  font-weight: 600;
}
</style>
