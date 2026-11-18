<script setup lang="ts">
// The statistics card over the map, opened from the map's menu (components/MapMenu.vue, Statistics): a graph of the packets heard by the hour over the last day, each bar made of the parts of the radios that
// heard them and of the internet (the daemon is asked for `packet_stats` when the card opens and every minute after; components/TrendChart.vue draws the bars; until the first answer the graph is its empty frame,
// so that nothing moves when it comes), then what the page has heard, counted up (lib/stats.ts, lib/packetstats.ts) in sections of a few lines each, each a heading that folds what is under it: the stations, how far
// we reach, the packets, each radio over the last day (with the colour of its part of the bars), what we sent, what went through us, and the radios since the daemon started. Which sections are folded is remembered
// by this browser. It is at the bottom right of the map, clear of the station cards at the left, and moves as the station book, the packets and the status do. Its cross closes it, and so does Esc with the
// station cards; whether it is open is remembered by this browser (composables/useAppShell.ts), so it comes back with the page. On a tablet and a desktop (`movable`) it can be dragged by its head anywhere over the map, or moved with Alt
// and the arrow keys, and where it was left is remembered too (composables/useFreeDrag.ts). On a phone it is a card at the bottom of the screen like the station's.
import { computed, onMounted, ref, watch } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import IconButton from "@/components/IconButton.vue";
import TrendChart from "@/components/TrendChart.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useFreeDrag } from "@/composables/useFreeDrag";
import { usePersistedText } from "@/composables/usePersisted";
import { t } from "@/i18n";
import { useRadios } from "@/composables/useRadios";
import { CHART_HOURS, chartOf } from "@/lib/packetstats";
import { emptyHistory, mapStats } from "@/lib/stats";
import type { PacketRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ packets: ReadonlyMap<string, PacketRow>; movable?: boolean }>(), { movable: false });
const emit = defineEmits<{ close: [] }>();
const page = useDaemonContext();
const root = ref<HTMLElement | null>(null);
const drag = useFreeDrag(root, "statsplace", () => props.movable);

const radios = useRadios();
const sections = computed(() =>
  mapStats({
    stations: page.stations.value,
    packets: props.packets,
    status: page.status.value,
    radios: radios.all.value,
    igate: page.igate.value,
    map: page.map.value,
    aging: page.aging.value,
    now: page.now.value,
    packetStats: page.packetStats.value,
  }),
);

/** The bars of the graph, from the latest answer of the daemon; the empty frame of the same hours until one came. */
const chart = computed(() => {
  const stats = page.packetStats.value;
  return stats === null ? { ...emptyHistory(page.now.value, CHART_HOURS), parts: [] } : chartOf(stats, radios.all.value);
});

/** The sections the person folded, by their title, remembered by this browser. */
const foldedText = usePersistedText("statsfolded", "", 400);
const folded = computed(() => new Set(foldedText.value.split(",").filter((one) => one !== "")));
function fold(title: string, open: boolean): void {
  const next = new Set(folded.value);
  if (open) next.delete(title);
  else next.add(title);
  foldedText.value = [...next].join(",");
}

const ask = (): boolean => page.send({ cmd: "packet_stats" });
onMounted(ask);
// the counts move with the clock (the running hour grows, and at the top of the hour a bar is added): asked again each minute
watch(
  () => Math.floor(page.now.value / 60_000),
  () => void ask(),
);
</script>

<template>
  <section
    ref="root"
    class="card statscard"
    :class="{ moved: drag.moved.value, movable }"
    :style="drag.style.value"
    :aria-label="t('stats.label')"
    v-on="drag.on"
  >
    <header class="card-head" :title="movable ? t('station.card.drag_title') : undefined">
      <div class="card-title">
        <span class="card-call"
          ><strong>{{ t("stats.title") }}</strong></span
        >
      </div>
      <IconButton kind="close" class="card-close" :label="t('iconbutton.close')" @click="emit('close')" />
    </header>
    <div class="card-body">
      <div class="stats-chart">
        <TrendChart
          :title="t('stats.chart')"
          :unit="t('stats.chart_unit')"
          :from="chart.from"
          :to="chart.to"
          :main="chart.points"
          :parts="chart.parts"
          as-bars
          zero
          tone="packets"
          :value-decimals="0"
        />
      </div>
      <DisclosureBox
        v-for="section in sections"
        :key="section.title"
        plain
        class="stats-fold"
        summary-class="stats-section"
        :title="t(section.title)"
        :open="!folded.has(section.title)"
        @folded="(open) => fold(section.title, open)"
      >
        <dl class="card-fields">
          <template v-for="line in section.lines" :key="line.key ?? line.label">
            <dt><span v-if="line.tone" class="stats-swatch" :class="line.tone" aria-hidden="true"></span>{{ t(line.label, line.params) }}</dt>
            <dd>{{ line.value }}</dd>
          </template>
        </dl>
      </DisclosureBox>
    </div>
  </section>
</template>
