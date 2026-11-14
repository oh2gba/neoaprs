<script setup lang="ts">
// The receive level of the HF radio's audio, one row of the scope: a bar with its good range, and the number. The level comes with every row of the waterfall (the page's `scopeRows`) while `on` (the caller asks for the rows), and from the
// newest of the rows the daemon kept when they come; while the radio transmits the rows are of our own signal, so the bar is dimmed and holds the last level received. The box in Settings (components/HfScope.vue) has the (i) of it (`tip`); the monitor card over the map (components/MonitorCard.vue) has the row alone.
import { computed, onBeforeUnmount, ref, useId, watch } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import { GOOD_PERCENT, dbText, levelPercent, levelZone } from "@/lib/hflevel";
import type { ScopeRow } from "@/lib/scoperow";

const props = defineProps<{ on: boolean; tip?: boolean }>();
const { scopeRows } = useDaemonContext();
const id = useId();
const level = ref<number | null>(null);
const transmitting = ref(false);
let stop: (() => void) | null = null;

/** Listens to the rows while they are asked for: the level starts again with them. */
function listen(on: boolean): void {
  stop?.();
  stop = null;
  transmitting.value = false;
  if (!on) return;
  level.value = null;
  const take = (row: ScopeRow): void => {
    transmitting.value = row.tx;
    if (!row.tx) level.value = row.level;
  };
  stop = scopeRows.listen({
    row: (kept) => take(kept.row),
    whole: () => {
      const rows = scopeRows.rows;
      let i = rows.length - 1;
      while (i >= 0 && rows[i].row.tx) i--;
      level.value = i >= 0 ? rows[i].row.level : null;
      transmitting.value = rows.at(-1)?.row.tx ?? false;
    },
  });
}
watch(() => props.on, listen, { immediate: true });
onBeforeUnmount(() => listen(false));

const zone = computed(() => (level.value === null ? "low" : levelZone(level.value)));
const fill = computed(() => `${level.value === null ? 0 : levelPercent(level.value)}%`);
const good = computed(() => ({ left: `${GOOD_PERCENT[0]}%`, width: `${GOOD_PERCENT[1] - GOOD_PERCENT[0]}%` }));
</script>

<template>
  <div class="field">
    <label :for="id">{{ t("settings.scope.level") }}</label>
    <div class="field-control scope-level">
      <div :id="id" class="levelbar" :class="{ held: transmitting }" role="meter" :aria-label="t('settings.scope.level')">
        <span class="levelgood" :style="good"></span>
        <span class="levelfill" :class="zone" :style="{ width: fill }"></span>
      </div>
      <output class="mono levelvalue">{{ t("settings.scope.value", { value: dbText(level) }) }}</output>
      <InfoTip v-if="tip" :label="t('settings.scope.tip_label')" picture="scope"
        ><span class="info-line">{{ t("settings.scope.tip1") }}</span
        ><span class="info-line">{{ t("settings.scope.tip2") }}</span></InfoTip
      >
    </div>
  </div>
</template>

<style scoped>
.scope-level {
  display: flex;
  align-items: center;
  gap: 8px;
}
.levelbar {
  position: relative;
  flex: 1 1 auto;
  min-width: 60px;
  height: 10px;
  overflow: hidden;
  background: var(--input-bg);
  border: 1px solid var(--border);
  border-radius: 5px;
}
.levelbar.held {
  opacity: 0.45;
}
.levelgood {
  position: absolute;
  top: 0;
  bottom: 0;
  background: var(--ok-soft-bg);
}
.levelfill {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  transition: width 0.2s linear;
}
.levelfill.low {
  background: var(--muted);
}
.levelfill.good {
  background: var(--ok);
}
.levelfill.high {
  background: var(--warn);
}
.levelfill.clip {
  background: var(--bad);
}
.levelvalue {
  flex: 0 0 auto;
  min-width: 9ch;
  text-align: right;
}
@media (prefers-reduced-motion: reduce) {
  .levelfill {
    transition: none;
  }
}
</style>
