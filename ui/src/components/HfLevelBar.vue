<script setup lang="ts">
// The receive level of a radio's audio, one row of the scope: a bar with its good range and the
// number. The level comes from the waterfall rows of `radio` while `on`. While the radio
// transmits the bar is dimmed and holds the last level received. The Settings box (HfScope.vue)
// adds the (i) (`tip`) and the capture-level slider (`card`); the monitor card (MonitorCard.vue)
// shows the row alone.
import { computed, onBeforeUnmount, ref, useId, watch } from "vue";
import CardSlider from "@/components/CardSlider.vue";
import InfoTip from "@/components/InfoTip.vue";
import LevelBar from "@/components/LevelBar.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import { GOOD_PERCENT, dbText, levelPercent, levelZone } from "@/lib/hflevel";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import type { PageRadio, RadioId } from "@/lib/radios";
import type { ScopeRow } from "@/lib/scoperow";

const props = defineProps<{
  on: boolean;
  radio: RadioId | null;
  tip?: boolean;
  card?: { radio: PageRadio; form: SettingsFormState };
}>();
const { scopeOf } = useDaemonContext();
const id = useId();
const level = ref<number | null>(null);
const transmitting = ref(false);
let stop: (() => void) | null = null;

/** Listens to the rows while they are asked for; the level restarts with them. */
function listen(on: boolean): void {
  stop?.();
  stop = null;
  transmitting.value = false;
  if (!on || props.radio === null) return;
  level.value = null;
  const take = (row: ScopeRow): void => {
    transmitting.value = row.tx;
    if (!row.tx) level.value = row.level;
  };
  const memory = scopeOf(props.radio);
  stop = memory.listen({
    row: (kept) => take(kept.row),
    whole: () => {
      const rows = memory.rows;
      let i = rows.length - 1;
      while (i >= 0 && rows[i].row.tx) i--;
      level.value = i >= 0 ? rows[i].row.level : null;
      transmitting.value = rows.at(-1)?.row.tx ?? false;
    },
  });
}
watch(
  () => [props.on, props.radio] as const,
  ([on]) => listen(on),
  { immediate: true },
);
onBeforeUnmount(() => listen(false));

/** The card's own capture level, where the box has the slider for it. */
const capture = computed(() => (props.card?.radio.row.card.read ? props.card.radio.row.card.rx : null));
const zone = computed(() => (level.value === null ? "low" : levelZone(level.value)));
const fill = computed(() => (level.value === null ? 0 : levelPercent(level.value)));
</script>

<template>
  <LevelBar
    :id="id"
    :label="t('settings.scope.level')"
    :percent="fill"
    :zone="zone"
    :good="GOOD_PERCENT"
    :held="transmitting"
    :value="t('settings.scope.value', { value: dbText(level) })"
  >
    <template v-if="card" #control
      ><CardSlider
        :label="t('settings.cardlevel.rx_label')"
        :setting-key="`radio/${card.radio.id}/rx_card`"
        :level="capture"
        :form="card.form"
    /></template>
    <InfoTip v-if="tip" :label="t('settings.scope.tip_label')" picture="scope"
      ><span class="info-line">{{ t("settings.scope.tip1") }}</span
      ><span class="info-line">{{ t("settings.scope.tip2") }}</span></InfoTip
    >
  </LevelBar>
</template>
