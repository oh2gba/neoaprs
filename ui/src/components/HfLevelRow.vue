<script setup lang="ts">
// The Transmit level of an HF radio, a row under Tune: the gain the modem sends its audio to the radio with, in whole dB (the radio's setting `radio/<id>/tx_gain_db`, the key given), lowered and raised by the two buttons, each press saved at once. The modem takes it while it runs, and
// the tune tone follows it, so the operator presses Tune and watches the radio's ALC while the level moves. Beside it the peak of the latest transmission in dBFS (the modem's own reading), which turns orange at 0 or over, where the sound card clips.
// The room of the number is kept, so that nothing moves when it changes. The range is the field's of the radio's type, the modem the radio's row. A modem that says no peak (a Sound card radio's Direwolf: `can.scope` is the modem giving its audio) has the row without it.
import InfoTip from "@/components/InfoTip.vue";
import { computed } from "vue";
import type { Settings } from "@/composables/useSettings";
import type { SettingsFormState } from "@/composables/useSettingsForm";
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
/** Whether the modem says the peak of what it sends: one that gives its audio (the HF modem, whose scope and peak come the same way); a Sound card radio's Direwolf gives none. */
const peakShown = computed(() => props.radio.row.can.scope);

function move(by: number): void {
  const next = Math.max(min.value, Math.min(max.value, gain.value + by));
  if (next !== gain.value) props.form.choose({ [props.settingKey]: String(next) });
}
</script>

<template>
  <div class="field txlevel">
    <label :for="`${id}-up`">{{ t("settings.txlevel.label") }}</label>
    <div class="field-control txlevel-control">
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
      <InfoTip :label="t('settings.txlevel.tip_label')"
        ><span class="info-line">{{ t("settings.txlevel.tip1") }}</span
        ><span v-if="peakShown" class="info-line">{{ t("settings.txlevel.tip2") }}</span></InfoTip
      >
    </div>
    <output v-if="peakShown" class="mono txlevel-peak" :class="{ clip: clips(peak) }">{{ t("settings.txlevel.peak", { value: dbText(peak) }) }}</output>
  </div>
</template>

<style scoped>
.txlevel-control {
  display: flex;
  align-items: center;
  gap: 8px;
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
