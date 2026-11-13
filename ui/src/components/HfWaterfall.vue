<script setup lang="ts">
// The HF radio's waterfall on a canvas, drawn as a rig draws it (lib/waterfall.ts, lib/waterfallpainter.ts): the frequency ruler with the band of a frame as a bracket, the waterfall at the modem's own bins scrolled one line at a time, the spectrum
// as a curve with its average and the floor on a faint grid of dB, the time at the left edge, and what was heard written on the line its frame ended (its call and SNR; our own transmissions are a mark at the edge). The rows
// are the daemon's (`onScopeRow`), each over the floor the page finds from them (lib/waterfallfloor.ts); they come only while `on` (the caller asks for them), and the picture starts again each time they do. Two minutes are kept,
// so that the canvas is drawn again whole when its size changes; a canvas that is not shown is not drawn on. It has no controls: the floor and the passband's shape are followed by themselves.
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import { snrText } from "@/lib/waterfall";
import { RowFeed } from "@/lib/waterfallfloor";
import { Waterfall } from "@/lib/waterfallpainter";
import type { PacketRow } from "@/protocol/protocol";

const props = defineProps<{ on: boolean }>();
/** Whether the canvas has room (it has none in a fold that is closed, under another tab or in a panel a phone does not show): the pane that holds it looks at the scope only while it does. */
const emit = defineEmits<{ shown: [shown: boolean] }>();
const { onScopeRow, packets, hf } = useDaemonContext();
const canvas = ref<HTMLCanvasElement | null>(null);
const feed = new RowFeed();
let painter: Waterfall | null = null;
let stop: (() => void) | null = null;
let seen = 0; // the newest packet that is not written on the picture: what was there when the rows began, and every one since

/** The newest packet's number: they count up in the order they came (in this run of the daemon). */
const newest = (): number => {
  let id = 0;
  for (const row of packets.values()) id = Math.max(id, row.id);
  return id;
};

/** A frame heard on the HF radio itself (not one from the internet, nor one of ours). */
const heardOnHf = (row: PacketRow): boolean => row.radio === "hf" && row.direction === "in" && row.via !== "is";

function listen(on: boolean): void {
  stop?.();
  stop = null;
  if (!on || !painter) return;
  feed.clear();
  painter.clear();
  seen = newest();
  stop = onScopeRow((row) => {
    const at = Date.now();
    const { bytes, tx } = feed.take(row, at);
    painter?.push(bytes, at, tx);
  });
}

// what was heard is written on the line where the frame ended: its call and the modem's SNR of it (the SNR of the latest frame decoded, which the modem says before the frame)
watch(newest, (id) => {
  if (id < seen) seen = id; // (the daemon was started again: its packets count from the start)
  if (!stop || id <= seen) return;
  const snr = hf.value?.modem?.snr ?? null;
  for (const row of [...packets.values()].filter((row) => row.id > seen && heardOnHf(row)).sort((a, b) => a.id - b.id))
    painter?.label(snr === null ? row.source : t("settings.scope.heard", { call: row.source, db: snrText(snr) }));
  seen = id;
});

watch(() => props.on, listen);
let observer: ResizeObserver | null = null;
const report = (): void => emit("shown", (canvas.value?.clientWidth ?? 0) > 0);
onMounted(() => {
  if (!canvas.value) return;
  painter = new Waterfall(canvas.value);
  if (typeof ResizeObserver === "function") {
    observer = new ResizeObserver(() => {
      painter?.draw();
      report();
    });
    observer.observe(canvas.value);
  }
  report();
  if (props.on) listen(true);
  else painter.draw(); // (the ruler and the empty curve: the rows start the picture again when they come)
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
