<script setup lang="ts">
// The receive level of a radio's audio, one row of the scope: a bar with its good range, and the number. The level comes with every row of the waterfall of `radio` (the page's memory of that radio's rows; null while no radio has a scope: no level) while `on` (the caller asks for the rows), and from the
// newest of the rows the daemon kept when they come; while the radio transmits the rows are of our own signal, so the bar is dimmed and holds the last level received (the bar is components/LevelBar.vue). The box in Settings (components/HfScope.vue) has the (i) of it (`tip`); the monitor card over the map (components/MonitorCard.vue) has the row alone.
import { computed, onBeforeUnmount, ref, useId, watch } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import LevelBar from "@/components/LevelBar.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import { GOOD_PERCENT, dbText, levelPercent, levelZone } from "@/lib/hflevel";
import type { RadioId } from "@/lib/radios";
import type { ScopeRow } from "@/lib/scoperow";

const props = defineProps<{ on: boolean; radio: RadioId | null; tip?: boolean }>();
const { scopeOf } = useDaemonContext();
const id = useId();
const level = ref<number | null>(null);
const transmitting = ref(false);
let stop: (() => void) | null = null;

/** Listens to the rows while they are asked for: the level starts again with them. */
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
    <InfoTip v-if="tip" :label="t('settings.scope.tip_label')" picture="scope"
      ><span class="info-line">{{ t("settings.scope.tip1") }}</span
      ><span class="info-line">{{ t("settings.scope.tip2") }}</span></InfoTip
    >
  </LevelBar>
</template>
