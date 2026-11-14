<script setup lang="ts">
// The HF radio's waterfall on a canvas, drawn as a rig draws it (lib/waterfall.ts, lib/waterfallpainter.ts): the frequency ruler with the band of a frame as a bracket, the waterfall at the modem's own bins scrolled one line at a time, the spectrum
// as a curve with its average and the floor on a faint grid of dB, the time at the left edge, and what was heard written on the line of the moment it was heard (its call and SNR; our own transmissions are a mark at the edge). The rows
// and the stations heard are what the page keeps (`scopeRows`, lib/scopememory.ts: two minutes, each row at the moment it was made, over the page's one floor), so the picture is drawn whole at once when it is mounted, and again
// when the rows the daemon kept come; the rows that come after are drawn as they come (the caller asks for them). A canvas that is not shown is not drawn on, and is drawn whole when it has room. It has no controls: the floor
// and the passband's shape are followed by themselves.
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import type { Heard } from "@/lib/scopememory";
import { snrText } from "@/lib/waterfall";
import { slotOf } from "@/lib/waterfalllines";
import { Waterfall } from "@/lib/waterfallpainter";

/** Whether the canvas has room (it has none in a fold that is closed, under another tab or in a panel a phone does not show): the pane that holds it looks at the scope only while it does. */
const emit = defineEmits<{ shown: [shown: boolean] }>();
const { scopeRows, scope } = useDaemonContext();
const canvas = ref<HTMLCanvasElement | null>(null);
let painter: Waterfall | null = null;
let stop: (() => void) | null = null;

/** What is written for a station heard: its call and the modem's SNR of it, or the call alone where the page did not read one. */
const text = (heard: Heard): string => (heard.snr === null ? heard.call : t("settings.scope.heard", { call: heard.call, db: snrText(heard.snr) }));

/** The whole picture from what the page keeps, as it stands now. */
let drawn = ""; // what the whole picture was last drawn of: the line of its moment, the rows and the stations heard
function whole(force = true): void {
  const now = scopeRows.now();
  const of = `${slotOf(now)} ${scopeRows.rows.length} ${scopeRows.rows.at(-1)?.at} ${scopeRows.heard.length}`;
  if (!painter || (!force && of === drawn)) return; // (asked again in the moment it was drawn: the same picture)
  drawn = of;
  painter.show(
    scopeRows.rows,
    scopeRows.heard.map((heard) => ({ at: heard.at, text: text(heard) })),
    now,
  );
}

// the rows are asked for again (the page is in front again, the socket open anew): the picture as it stands now at once, the time it was away at the top until the daemon's rows fill it, so that nothing moves when they come
watch(scope.wanted, (on) => on && whole(false));

let observer: ResizeObserver | null = null;
let roomy = false;
/** Says whether the canvas has room; true when it has just got it again. */
const report = (): boolean => {
  const now = (canvas.value?.clientWidth ?? 0) > 0;
  const back = now && !roomy;
  roomy = now;
  emit("shown", now);
  return back;
};
onMounted(() => {
  if (!canvas.value) return;
  painter = new Waterfall(canvas.value);
  if (typeof ResizeObserver === "function") {
    observer = new ResizeObserver(() => {
      if (report())
        whole(); // (shown again: the picture as it stands now, the time it was away at the top until the daemon's rows fill it)
      else painter?.draw();
    });
    observer.observe(canvas.value);
  }
  whole();
  stop = scopeRows.listen({
    row: (kept) => painter?.push(kept.bytes, kept.at, kept.tx),
    heard: (heard) => painter?.label(text(heard), heard.at),
    whole,
  });
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
  background: var(--waterfall-0); /* the ground before the first line: no light box flashes before the picture */
}
</style>
