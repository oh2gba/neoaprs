<script setup lang="ts">
// A radio's waterfall on a canvas (lib/waterfall.ts, lib/waterfallpainter.ts): ruler, scrolling
// waterfall, spectrum curve and the stations heard written on the line of their moment. Rows and
// stations come from the page's memory (`scopeOf`, lib/scopememory.ts), so the picture is drawn
// whole on mount and when the daemon's rows arrive, then row by row; a canvas that is not shown
// is redrawn whole when it has room, and when it grew taller than the lines it held. `speed` is the
// monitor card's choice (MonitorMenu.vue).
// `radio` is the radio shown (null: ruler and background only).
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import type { RadioId } from "@/lib/radios";
import { ScopeMemory, type Heard } from "@/lib/scopememory";
import { snrText, type Speed } from "@/lib/waterfall";
import { Waterfall } from "@/lib/waterfallpainter";

const props = withDefaults(defineProps<{ speed?: Speed; radio: RadioId | null }>(), { speed: "normal" });

/** Whether the canvas has room (not in a closed fold, under another tab or in a hidden phone
 * panel); the pane looks at the scope only while it does. `reach`: how many ms the picture shows
 * (0 while it has no room), told before `shown`. */
const emit = defineEmits<{ shown: [shown: boolean]; reach: [ms: number] }>();
const { scopeOf, scope } = useDaemonContext();
const canvas = ref<HTMLCanvasElement | null>(null);
let painter: Waterfall | null = null;
let stop: (() => void) | null = null;

/** The text for a heard station: its call and the modem's SNR, or the call alone without one. */
const text = (heard: Heard): string =>
  heard.snr === null ? heard.call : t("settings.scope.heard", { call: heard.call, db: snrText(heard.snr) });
/** The radio shown, and what the page keeps of it. */
const NOTHING = new ScopeMemory();
const memoryOf = (radio: RadioId | null): ScopeMemory => (radio === null ? NOTHING : scopeOf(radio));
let memory = memoryOf(props.radio);

/** The whole picture from what the page keeps, as it stands now. */
let drawn = ""; // what the picture was last drawn of
function whole(force = true): void {
  const now = memory.now();
  if (!painter) return;
  const of = `${props.speed} ${painter.slot(now)} ${props.radio} ${memory.rows.length} ${memory.rows.at(-1)?.at} ${memory.heard.length}`;
  if (!force && of === drawn) return;
  drawn = of;
  painter.show(
    memory.rows,
    memory.heard.map((heard) => ({ at: heard.at, text: text(heard) })),
    now,
  );
}

// The rows are requested again (page in front, socket reopened): redraw at once so that nothing
// moves when they arrive.
watch(
  () => props.radio !== null && scope.asked.value.includes(props.radio),
  (on) => on && whole(false),
);
/** Listens to what is kept of the shown radio. */
function listen(): void {
  stop?.();
  stop = memory.listen({
    row: (kept) => painter?.push(kept.bytes, kept.at, kept.tx),
    heard: (heard) => painter?.label(text(heard), heard.at),
    whole,
  });
}
// another radio shown: redraw at once, then rows as they come
watch(
  () => props.radio,
  (radio) => {
    memory = memoryOf(radio);
    listen();
    whole();
  },
);
let reach = 0;
/** Tell how long the picture is when that changed. */
function tell(): void {
  const now = painter?.reach() ?? 0;
  if (now !== reach) emit("reach", (reach = now));
}
// another speed: the same rows drawn again in place at once
watch(
  () => props.speed,
  (speed) => {
    painter?.setSpeed(speed);
    whole();
    tell();
  },
);

let observer: ResizeObserver | null = null;
let roomy = false;
/** Update whether the canvas has room; true when it has just regained it. */
const room = (): boolean => {
  const now = (canvas.value?.clientWidth ?? 0) > 0;
  const back = now && !roomy;
  roomy = now;
  return back;
};
const report = (): void => {
  tell();
  emit("shown", roomy);
};
onMounted(() => {
  if (!canvas.value) return;
  painter = new Waterfall(canvas.value, props.speed);
  if (typeof ResizeObserver === "function") {
    observer = new ResizeObserver(() => {
      // Regained room, or taller than the lines held: drawn whole from the rows kept, so the top stays.
      if (room() || painter?.draw()) whole();
      report();
    });
    observer.observe(canvas.value);
  }
  whole();
  listen();
  room();
  report();
});
onBeforeUnmount(() => {
  observer?.disconnect();
  stop?.();
  emit("shown", false);
});
</script>

<template>
  <canvas ref="canvas" class="hf-waterfall" role="img" :aria-label="t('settings.scope.aria')"></canvas>
</template>

<style scoped>
.hf-waterfall {
  display: block;
  width: 100%;
  height: 100%;
  background: var(--waterfall-0); /* no light box flashes before the picture */
}
</style>
