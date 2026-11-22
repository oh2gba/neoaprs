<script setup lang="ts">
// The statistics card over the map, opened from the map menu: a graph of packets heard per hour
// over the last day (`packet_stats`, asked when the card opens and every minute; TrendChart
// draws it; an empty frame until the first answer so nothing moves), each bar split into the
// radios and the internet. Below are counts (lib/stats.ts, lib/packetstats.ts) in foldable
// sections: stations, reach, packets, each radio over the last day (with its bar colour), sent,
// forwarded, and radios since the daemon started. Folded sections and whether the card is open
// are remembered by the browser (composables/useAppShell.ts). It sits at the bottom right of
// the map; Esc and its cross close it. On a tablet or desktop (`movable`) its head drags it
// over the map, or Alt with the arrow keys moves it; the position is remembered too
// (composables/useFreeDrag.ts). On a phone it is a card at the bottom like the station's.
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

/** The graph bars from the latest answer; an empty frame over the same hours until then. */
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
// The counts move with the clock, so ask again each minute.
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
