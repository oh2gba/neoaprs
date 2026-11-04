<script setup lang="ts">
// The scope of the HF radio's box, folded away under one row (the page's fold, DisclosureBox, remembered in this browser): a waterfall of the radio's audio from 300 to 2700 Hz on a canvas, the signal band of a frame (1.2 to 1.8 kHz above
// the dial) marked as a faint block, and under it the receive level as a bar with its good range, and the number. A picture arrives five times a second and becomes the top row, the older ones moving down, so that a signal is a trace down the
// picture and a frame a block; while the radio transmits the rows are of our own signal (drawn grey to white, apart from the colour scale of what is received) and the level stays at the last one received. The rows start again each time the pictures do (the fold opened, the socket
// open anew). The pictures are asked of the daemon only while the fold is open (composables/useHfScope.ts); a modem without the interface has no scope, and this is not there.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import InfoTip from "@/components/InfoTip.vue";
import { useHfScope } from "@/composables/useHfScope";
import { t } from "@/i18n";
import { GOOD_PERCENT, addRow, dbText, drawWaterfall, heat, levelPercent, levelZone, type Row } from "@/lib/scope";

const scope = useHfScope();
const canvas = ref<HTMLCanvasElement | null>(null);
let rows: Row[] = [];
const FLOOR = heat(0); // the background before the first row, the colour of the floor: no light box flashes before the picture

function paint(): void {
  if (canvas.value) drawWaterfall(canvas.value, rows);
}

watch(scope.picture, (picture) => {
  rows = picture === null ? [] : addRow(rows, { bins: picture.bins.slice(), tx: picture.tx });
  paint();
});
// a fold that was closed has no width: it is drawn when it opens, and again when the box is resized
watch(scope.open, async () => {
  await nextTick();
  paint();
});
let observer: ResizeObserver | null = null;
onMounted(() => {
  paint();
  if (typeof ResizeObserver === "function" && canvas.value) {
    observer = new ResizeObserver(paint);
    observer.observe(canvas.value);
  }
});
onBeforeUnmount(() => observer?.disconnect());

const level = computed(() => scope.level.value);
const zone = computed(() => (level.value === null ? "low" : levelZone(level.value)));
const fill = computed(() => `${level.value === null ? 0 : levelPercent(level.value)}%`);
const good = computed(() => ({ left: `${GOOD_PERCENT[0]}%`, width: `${GOOD_PERCENT[1] - GOOD_PERCENT[0]}%` }));
</script>

<template>
  <DisclosureBox v-if="scope.available.value" class="hf-scope" :title="t('settings.scope.title')" :open="scope.open.value" @folded="scope.open.value = $event">
    <canvas ref="canvas" class="scope-canvas" role="img" :aria-label="t('settings.scope.aria')"></canvas>
    <div class="field">
      <label for="hf-scope-level">{{ t("settings.scope.level") }}</label>
      <div class="field-control scope-level">
        <div id="hf-scope-level" class="levelbar" :class="{ held: scope.transmitting.value }" role="meter" :aria-label="t('settings.scope.level')">
          <span class="levelgood" :style="good"></span>
          <span class="levelfill" :class="zone" :style="{ width: fill }"></span>
        </div>
        <output class="mono levelvalue">{{ t("settings.scope.value", { value: dbText(level) }) }}</output>
        <InfoTip :label="t('settings.scope.tip_label')" picture="scope"
          ><span class="info-line">{{ t("settings.scope.tip1") }}</span
          ><span class="info-line">{{ t("settings.scope.tip2") }}</span></InfoTip
        >
      </div>
    </div>
  </DisclosureBox>
</template>

<style scoped>
.scope-canvas {
  display: block;
  width: 100%;
  height: 72px;
  margin-bottom: 8px;
  background: v-bind(FLOOR);
  border: 1px solid var(--border);
  border-radius: 4px;
}
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
