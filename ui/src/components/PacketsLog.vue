<script setup lang="ts">
// The packets as they arrive, newest first: the time, whether it was heard ("in") or sent by us ("out"), the packet as a TNC2 line, the route it came by ("via OH2RCH-2", "direct", "via OH7JHF-1 (internet)" for a packet an iGate put on the air; empty for one we sent) and what the daemon made of it. A filter box narrows
// the list; a click on a packet opens it in plain facts (components/PacketDetail.vue), with what the parser decoded of it, as JSON, under "Raw". A route breaks between its words, never inside a callsign.
import { computed, ref } from "vue";
import { t } from "@/i18n";
import PacketDetail from "@/components/PacketDetail.vue";
import RouteText from "@/components/RouteText.vue";
import { clockText } from "@/lib/format";
import { filterPackets, newestFirst } from "@/lib/packets";
import { routeWords } from "@/lib/routes";
import type { PacketRow } from "@/protocol/protocol";

const props = defineProps<{ packets: ReadonlyMap<string, PacketRow> }>();

const filter = ref("");
const open = ref<number | null>(null);

const rows = computed(() => filterPackets(newestFirst(props.packets.values()), filter.value));

function toggle(id: number): void {
  open.value = open.value === id ? null : id;
}
</script>

<template>
  <div class="tablepane">
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
      <table class="grid packets">
        <thead>
          <tr>
            <th>{{ t("packets.col.time") }}</th>
            <th>{{ t("packets.col.dir") }}</th>
            <th>{{ t("packets.col.packet") }}</th>
            <th>{{ t("packets.col.route") }}</th>
            <th>{{ t("packets.col.summary") }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in rows" :key="row.id">
            <tr :class="{ selected: open === row.id, out: row.direction === 'out' }" tabindex="0" @click="toggle(row.id)" @keydown.enter="toggle(row.id)">
              <td class="mono nowrap">{{ clockText(row.heard_at) }}</td>
              <td :class="row.direction">{{ t(`packets.dir.${row.direction}`) }}</td>
              <td class="mono wrap">{{ row.tnc2 }}</td>
              <td class="muted route-cell"><RouteText :text="routeWords(row.route)" /></td>
              <td class="wrap">{{ row.summary }}</td>
            </tr>
            <tr v-if="open === row.id" class="detail">
              <td colspan="5">
                <PacketDetail :row="row" />
              </td>
            </tr>
          </template>
          <tr v-if="rows.length === 0">
            <td colspan="5" class="empty">{{ packets.size === 0 ? t("packets.none_yet") : t("packets.none_match") }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="foot muted">{{ t("packets.count", { shown: rows.length, n: packets.size }) }}</div>
  </div>
</template>
