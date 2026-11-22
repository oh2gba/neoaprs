<script setup lang="ts">
// The Nearby tab: four lists from the stations already heard (rules in lib/nearby.ts), nearest
// first with distance and bearing: digipeaters, voice frequencies, iGates and stations heard
// direct. A click selects the station as in the Stations table (NearbyTable.vue). Above them Ask
// around (NearbyAsk.vue) asks the stations in range to make themselves known; their answers fill
// the lists.
import { computed } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import NearbyAsk from "@/components/NearbyAsk.vue";
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

defineProps<{ selected: string | null; others?: readonly string[] }>();
const emit = defineEmits<{ select: [call: string, multi?: boolean] }>();
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
    tip: { label: t("nearby.digipeaters_tip_label"), text: t("nearby.digipeaters_tip"), picture: "range" as const },
    items: digis.value.map((d: Digipeater): NearbyItem => ({ call: d.call, row: d.row, lines: digipeaterLines(d) })),
  },
  { id: "voice", title: t("nearby.voice"), help: t("nearby.voice_help"), tip: null, items: itemsOf(voiceRows(rows.value), voiceLines) },
  {
    id: "igates",
    title: t("nearby.igates"),
    help: t("nearby.igates_help"),
    tip: { label: t("nearby.igates_tip_label"), text: t("nearby.igates_tip"), picture: "igate" as const },
    items: itemsOf(gateRows(rows.value), gateLines),
  },
  {
    id: "direct",
    title: t("nearby.direct"),
    help: t("nearby.direct_help"),
    tip: null,
    items: itemsOf(directRows(rows.value), (row) => directLines(row, now.value)),
  },
]);
</script>

<template>
  <div class="nearbypane">
    <NearbyAsk />
    <fieldset v-for="section in sections" :key="section.id" class="nearby-section">
      <legend class="nearby-head">
        {{ section.title }} <span class="muted">{{ section.items.length }}</span>
        <InfoTip v-if="section.tip" :label="section.tip.label" :picture="section.tip.picture">{{ section.tip.text }}</InfoTip>
      </legend>
      <p class="muted nearby-help">{{ section.help }}</p>
      <p v-if="section.items.length === 0" class="empty nearby-empty">{{ t("nearby.none_yet") }}</p>
      <NearbyTable
        v-else
        :items="section.items"
        :selected="selected"
        :others="others"
        :label="section.title"
        @select="(call, multi) => emit('select', call, multi)"
      />
    </fieldset>
  </div>
</template>
