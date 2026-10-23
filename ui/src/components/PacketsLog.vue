<script setup lang="ts">
// The packets as they arrive, newest first: the time, whether it was heard ("in") or sent by us ("out"), the packet as a TNC2 line, the route it came by ("via OH2RCH-2", "direct", "via OH7JHF-1 (internet)" for a packet an iGate put on the air; empty for one we sent) and what the daemon made of it. A filter box narrows
// the list; a click on a packet opens what the parser decoded of it, as JSON, with the time the packet carries when it has one ("09 23:45 local" for a time the sender gave in its local clock).
import { computed, ref } from "vue";
import { clockText } from "@/lib/format";
import { sentTimeText } from "@/lib/details";
import { decodedJson, filterPackets, newestFirst } from "@/lib/packets";
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
      <input v-model="filter" class="input grow" type="search" placeholder="Filter" title="Call, text, kind" aria-label="Filter the packets" />
    </div>
    <div class="scroll">
      <table class="grid packets">
        <thead>
          <tr>
            <th>Time</th>
            <th>Dir</th>
            <th>Packet</th>
            <th>Route</th>
            <th>Summary</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in rows" :key="row.id">
            <tr :class="{ selected: open === row.id, out: row.direction === 'out' }" tabindex="0" @click="toggle(row.id)" @keydown.enter="toggle(row.id)">
              <td class="mono nowrap">{{ clockText(row.heard_at) }}</td>
              <td :class="row.direction">{{ row.direction }}</td>
              <td class="mono wrap">{{ row.tnc2 }}</td>
              <td class="wrap muted">{{ row.route }}</td>
              <td class="wrap">{{ row.summary }}</td>
            </tr>
            <tr v-if="open === row.id" class="detail">
              <td colspan="5">
                <div v-if="sentTimeText(row)" class="muted">Time in the packet: {{ sentTimeText(row) }}</div>
                <pre class="json">{{ decodedJson(row) }}</pre>
              </td>
            </tr>
          </template>
          <tr v-if="rows.length === 0">
            <td colspan="5" class="empty">{{ packets.size === 0 ? "No packet yet." : "No packet matches." }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="foot muted">{{ rows.length }} of {{ packets.size }} packets</div>
  </div>
</template>
