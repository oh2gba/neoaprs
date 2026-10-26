<script setup lang="ts">
// The packets as they arrive, newest first: the time, whether it was heard ("in") or sent by us ("out"), the channel it came by (RF, iGate, Internet: lib/channels.ts; ours go by RF), the packet as a TNC2 line, the route it came by ("via OH2RCH-2", "direct", "via OH7JHF-1 (internet)" for a packet an iGate put on the air; empty for one we sent) and what the daemon made of it. A filter box narrows
// the list; a click on a packet opens it in plain facts (components/PacketDetail.vue), with what the parser decoded of it, as JSON, under "Raw". A route breaks between its words, never inside a callsign.
// Laid out by the width of the tab itself (not of the window: the panel beside the map can be narrow on a wide screen; PACKETS_TABLE, lib/layout.ts): the table of columns when it is wide enough, else one block for each packet (the time, the direction and the channel,
// the packet line, then the route and the summary in small text) with the header row for a screen reader only; the click, the detail row and the filter are the same in both.
import { computed, ref } from "vue";
import { useElementWidth } from "@/composables/useElementWidth";
import { PACKETS_TABLE } from "@/lib/layout";
import { t } from "@/i18n";
import PacketDetail from "@/components/PacketDetail.vue";
import TabHelp from "@/components/TabHelp.vue";
import RouteText from "@/components/RouteText.vue";
import { packetLabel, packetTitle } from "@/lib/channels";
import { clockText } from "@/lib/format";
import { filterPackets, newestFirst } from "@/lib/packets";
import { routeWords } from "@/lib/routes";
import type { PacketRow } from "@/protocol/protocol";

const props = defineProps<{ packets: ReadonlyMap<string, PacketRow> }>();

const root = ref<HTMLElement | null>(null);
const width = useElementWidth(root);
/** The tab is narrower than the table needs (0 until it is measured: the table). */
const stacked = computed(() => width.value > 0 && width.value < PACKETS_TABLE);
const filter = ref("");
const open = ref<number | null>(null);

const rows = computed(() => filterPackets(newestFirst(props.packets.values()), filter.value));

function toggle(id: number): void {
  open.value = open.value === id ? null : id;
}
</script>

<template>
  <div ref="root" class="tablepane">
    <TabHelp :label="t('packets.about_label')">
      <span class="info-line">{{ t("packets.about1") }}</span>
      <span class="info-line">{{ t("packets.about2") }}</span>
    </TabHelp>
    <div class="toolbar">
      <input
        v-model="filter"
        class="input grow"
        type="search"
        :placeholder="t('packets.filter')"
        :title="t('packets.filter_title')"
        :aria-label="t('packets.filter_label')"
      />
    </div>
    <div class="scroll">
      <table class="grid packets" :class="{ stacked }">
        <thead :class="{ 'sr-only': stacked }">
          <tr>
            <th>{{ t("packets.col.time") }}</th>
            <th>{{ t("packets.col.dir") }}</th>
            <th>{{ t("packets.col.via") }}</th>
            <th>{{ t("packets.col.packet") }}</th>
            <th>{{ t("packets.col.route") }}</th>
            <th>{{ t("packets.col.summary") }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in rows" :key="row.id">
            <tr
              class="packet-row"
              :class="{ selected: open === row.id, out: row.direction === 'out' }"
              tabindex="0"
              @click="toggle(row.id)"
              @keydown.enter="toggle(row.id)"
            >
              <td class="mono nowrap time">{{ clockText(row.heard_at) }}</td>
              <td class="dir" :class="row.direction">{{ t(`packets.dir.${row.direction}`) }}</td>
              <td class="via" :class="{ internet: row.via === 'is' }" :title="packetTitle(row.via)">{{ packetLabel(row.via) }}</td>
              <td class="mono wrap line">{{ row.tnc2 }}</td>
              <td class="muted route-cell"><RouteText :text="routeWords(row.route)" /></td>
              <td class="wrap summary">{{ row.summary }}</td>
            </tr>
            <tr v-if="open === row.id" class="detail">
              <td colspan="6">
                <PacketDetail :row="row" />
              </td>
            </tr>
          </template>
          <tr v-if="rows.length === 0">
            <td colspan="6" class="empty">{{ packets.size === 0 ? t("packets.none_yet") : t("packets.none_match") }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="foot muted">{{ t("packets.count", { shown: rows.length, n: packets.size }) }}</div>
  </div>
</template>
