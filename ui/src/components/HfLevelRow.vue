<script setup lang="ts">
// The Transmit level of the HF radio, a row under Tune: the gain the modem sends its audio to the radio with, in whole dB (the setting `mercury/tx_gain_db`), lowered and raised by the two buttons, each press saved at once. The modem takes it while it runs, and
// the tune tone follows it, so the operator presses Tune and watches the radio's ALC while the level moves. Beside it the peak of the latest transmission in dBFS (the modem's own reading), which turns red at 0 or over, where the sound card clips.
// The room of the number is kept, so that nothing moves when it changes.
import InfoTip from "@/components/InfoTip.vue";
import { computed } from "vue";
import type { Settings } from "@/composables/useSettings";
import { useDaemonContext } from "@/composables/useDaemonContext";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { t } from "@/i18n";
import { clips, dbText, gainText } from "@/lib/hflevel";
import { LIMITS } from "@/protocol/lists";

const KEY = "mercury/tx_gain_db";
const props = defineProps<{ id: string; settings: Settings; form: SettingsFormState }>();
const { hf } = useDaemonContext();
const { min, max } = LIMITS.range[KEY];

const gain = computed(() => {
  const stored = Number.parseInt(props.settings.draft[KEY] ?? "", 10);
  return Number.isFinite(stored) ? stored : (hf.value?.modem?.tx_gain_db ?? 0);
});
const peak = computed(() => hf.value?.modem?.tx_peak_dbfs ?? null);

function move(by: number): void {
  const next = Math.max(min, Math.min(max, gain.value + by));
  if (next !== gain.value) props.form.choose({ [KEY]: String(next) });
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
        ><span class="info-line">{{ t("settings.txlevel.tip2") }}</span></InfoTip
      >
    </div>
    <output class="mono txlevel-peak" :class="{ clip: clips(peak) }">{{ t("settings.txlevel.peak", { value: dbText(peak) }) }}</output>
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
