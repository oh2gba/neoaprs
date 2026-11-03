<script setup lang="ts">
// The scope of the HF radio's box, folded away under one row (the page's fold, DisclosureBox, remembered in this browser): the spectrum of the radio's audio from 300 to 2700 Hz on a canvas, the signal band of a frame (1.2 to 1.8 kHz above the dial) marked as a faint
// block, and under it the receive level as a bar with its good range, and the number. A picture arrives five times a second and the drawing eases toward it, so that it moves smoothly; while the radio transmits the spectrum is of our own signal
// (drawn in the warning colour) and the level stays at the last one received. The pictures are asked of the daemon only while the fold is open (composables/useHfScope.ts); a modem without the interface has no scope, and this is not there.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import InfoTip from "@/components/InfoTip.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useHfScope } from "@/composables/useHfScope";
import { t } from "@/i18n";
import { GOOD_PERCENT, SCOPE_BINS, dbText, drawScope, ease, levelPercent, levelZone, scopeColours } from "@/lib/scope";

const scope = useHfScope();
const { dark } = useDaemonContext();
const canvas = ref<HTMLCanvasElement | null>(null);
const flat = (): number[] => new Array<number>(SCOPE_BINS).fill(0);
let shown = flat();
let target = flat();
let frame = 0;
const quiet = (): boolean => typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const next = (run: () => void): number => (typeof requestAnimationFrame === "function" ? requestAnimationFrame(run) : window.setTimeout(run, 16));
const stop = (id: number): void => (typeof cancelAnimationFrame === "function" ? cancelAnimationFrame(id) : window.clearTimeout(id));

function paint(): void {
  if (canvas.value) drawScope(canvas.value, shown, scopeColours(canvas.value, scope.transmitting.value));
}

function step(): void {
  frame = 0;
  const eased = ease(shown, target);
  shown = eased.values;
  paint();
  if (eased.moving) frame = next(step);
}

watch(scope.picture, (picture) => {
  target = picture === null ? flat() : picture.bins.slice();
  if (quiet()) {
    shown = target.slice();
    paint();
  } else if (frame === 0) {
    frame = next(step);
  }
});
// a fold that was closed has no width: it is drawn when it opens, and again when the colours change or the box is resized
watch([scope.open, dark, scope.transmitting], async () => {
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
onBeforeUnmount(() => {
  if (frame !== 0) stop(frame);
  observer?.disconnect();
});

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
  background: var(--input-bg);
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
