<script setup lang="ts">
// The statistics card over the map, opened from the map's menu (components/MapMenu.vue, Statistics): a graph of the packets heard by the hour over the last day (the daemon is asked for `packet_history` when the card
// opens and every minute after; components/TrendChart.vue draws the bars), then what the page has heard, counted up (lib/stats.ts) in sections of a few lines each, the stations, how far we reach, the packets and the
// radio since the daemon started. It is at the bottom right of the map, clear of the station cards at the left, and moves as the station book, the packets and the status do. Its cross closes it, and so does Esc with the
// station cards; whether it is open is remembered by this browser (composables/useAppShell.ts), so it comes back with the page. On a tablet and a desktop (`movable`) it can be dragged by its head anywhere over the map, or moved with Alt
// and the arrow keys, and where it was left is remembered too (composables/useFreeDrag.ts). On a phone it is a card at the bottom of the screen like the station's.
import { computed, onMounted, ref, watch } from "vue";
import IconButton from "@/components/IconButton.vue";
import TrendChart from "@/components/TrendChart.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useFreeDrag } from "@/composables/useFreeDrag";
import { t } from "@/i18n";
import { HISTORY_HOURS, historyPoints, mapStats } from "@/lib/stats";
import type { PacketRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ packets: ReadonlyMap<string, PacketRow>; movable?: boolean }>(), { movable: false });
const emit = defineEmits<{ close: [] }>();
const page = useDaemonContext();
const root = ref<HTMLElement | null>(null);
const drag = useFreeDrag(root, "statsplace", () => props.movable);

const sections = computed(() =>
  mapStats({
    stations: page.stations.value,
    packets: props.packets,
    status: page.status.value,
    tnc: page.tnc.value,
    igate: page.igate.value,
    map: page.map.value,
    aging: page.aging.value,
    now: page.now.value,
  }),
);

/** The bars of the graph, from the latest answer of the daemon; null until one came. */
const history = computed(() => (page.packetHistory.value === null ? null : historyPoints(page.packetHistory.value)));

const ask = (): boolean => page.send({ cmd: "packet_history", hours: HISTORY_HOURS });
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
      <div v-if="history" class="stats-chart">
        <TrendChart
          :title="t('stats.chart')"
          :unit="t('stats.chart_unit')"
          :from="history.from"
          :to="history.to"
          :main="history.points"
          as-bars
          zero
          tone="packets"
          :value-decimals="0"
        />
      </div>
      <template v-for="section in sections" :key="section.title">
        <h3 class="stats-section">{{ t(section.title) }}</h3>
        <dl class="card-fields">
          <template v-for="line in section.lines" :key="line.label">
            <dt>{{ t(line.label, line.params) }}</dt>
            <dd>{{ line.value }}</dd>
          </template>
        </dl>
      </template>
    </div>
  </section>
</template>
