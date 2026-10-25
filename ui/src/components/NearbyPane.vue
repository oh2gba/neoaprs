<script setup lang="ts">
// The Nearby tab: what is around us at a glance, in four lists from the stations already heard (lib/nearby.ts has the rules), each nearest first with the distance and bearing as the Stations table shows them, and "none yet" for a list that is empty:
// the digipeaters (what they repeated for us and the range they gave, with "Show range", which draws the range circle of each on the map), the voice frequencies that stations, objects and items gave and who reported them, the iGates, and the stations
// heard direct (the ones in simplex range). A click on a row selects the station like a click on the Stations table (NearbyTable.vue).
import { computed } from "vue";
import NearbyTable from "@/components/NearbyTable.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import {
  digipeaterLines,
  digipeaters,
  directLines,
  directRows,
  gateLines,
  gateRows,
  voiceLines,
  voiceRows,
  type Digipeater,
  type NearbyItem,
} from "@/lib/nearby";
import type { StationRow } from "@/protocol/protocol";

defineProps<{ selected: string | null; others?: readonly string[]; ranges: boolean }>();
const emit = defineEmits<{ select: [call: string, multi?: boolean]; "update:ranges": [on: boolean] }>();
const { stations, now } = useDaemonContext();

const rows = computed(() => [...stations.value.values()]);
const digis = computed(() => digipeaters(rows.value));

const itemsOf = (list: readonly StationRow[], lines: (row: StationRow) => string[]): NearbyItem[] =>
  list.map((row) => ({ call: row.call, row, lines: lines(row) }));
const sections = computed(() => [
  {
    id: "digipeaters",
    title: t("nearby.digipeaters"),
    help: t("nearby.digipeaters_help"),
    items: digis.value.map((d: Digipeater): NearbyItem => ({ call: d.call, row: d.row, lines: digipeaterLines(d) })),
  },
  { id: "voice", title: t("nearby.voice"), help: t("nearby.voice_help"), items: itemsOf(voiceRows(rows.value), voiceLines) },
  { id: "igates", title: t("nearby.igates"), help: t("nearby.igates_help"), items: itemsOf(gateRows(rows.value), gateLines) },
  { id: "direct", title: t("nearby.direct"), help: t("nearby.direct_help"), items: itemsOf(directRows(rows.value), (row) => directLines(row, now.value)) },
]);
</script>

<template>
  <div class="nearbypane">
    <section v-for="section in sections" :key="section.id" class="nearby-section" :aria-labelledby="`nearby-${section.id}`">
      <h3 :id="`nearby-${section.id}`" class="board-title">
        {{ section.title }} <span class="muted">{{ section.items.length }}</span>
      </h3>
      <p class="muted nearby-help">{{ section.help }}</p>
      <label v-if="section.id === 'digipeaters'" class="check nearby-ranges" :title="t('nearby.show_range_title')">
        <input type="checkbox" :checked="ranges" @change="emit('update:ranges', ($event.target as HTMLInputElement).checked)" />
        {{ t("nearby.show_range") }}
      </label>
      <p v-if="section.items.length === 0" class="empty nearby-empty">{{ t("nearby.none_yet") }}</p>
      <NearbyTable
        v-else
        :items="section.items"
        :selected="selected"
        :others="others"
        :label="section.title"
        @select="(call, multi) => emit('select', call, multi)"
      />
    </section>
  </div>
</template>
