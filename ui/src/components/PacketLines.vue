<script setup lang="ts">
// The packets as lines, newest first as they are given, the one look of the Packets tab (PacketsLog) and of a station's traffic in its panel (StationTraffic): the time, whether it was heard ("in") or sent by us ("out"), the
// channel it came by (RF, iGate, Internet: lib/channels.ts; ours go by RF), the packet as a TNC2 line, the route it came by ("via OH2RCH-2", "direct", "via OH7JHF-1 (internet)" for a packet an iGate put on the air; empty for
// one we sent) and what the daemon made of it, after which the slot `note` may add a word of the line's own (the state of a query in a station's traffic). A route breaks between its words, never inside a callsign. A click on
// a packet (or Enter) opens it under its line in plain facts (components/PacketDetail.vue), with what the parser decoded of it, as JSON, under "Raw"; again closes it. With `stacked` (the parent measures its width against
// PACKETS_TABLE, lib/layout.ts) each packet is one block (the time, the direction and the channel, the packet line, then the route and the summary in small text) and the header row is for a screen reader only. A right-click
// on a packet (a long press on a touch screen) offers to copy its line and the call that sent it (CopyMenu). `keyOf` tells the lines apart (the id, by default); the empty list says `empty`.
import TagMark from "@/components/TagMark.vue";
import { ref } from "vue";
import CopyMenu from "@/components/CopyMenu.vue";
import PacketDetail from "@/components/PacketDetail.vue";
import RouteText from "@/components/RouteText.vue";
import { useCopyMenu } from "@/composables/useCopyMenu";
import { t } from "@/i18n";
import { packetLabel, packetTitle, packetTone } from "@/lib/channels";
import { clockText } from "@/lib/format";
import { routeWords } from "@/lib/routes";
import type { PacketRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ rows: readonly PacketRow[]; stacked: boolean; empty: string; keyOf?: (row: PacketRow) => string }>(), {
  keyOf: (row: PacketRow) => String(row.id),
});
defineSlots<{ note?: (props: { row: PacketRow }) => unknown }>();

const open = ref<string | null>(null);
/** The copy menu of a line: the packet as its line of monitor text, and the call that sent it. */
const copy = useCopyMenu((line) => {
  const packet = props.rows.find((p) => props.keyOf(p) === line.dataset["key"]);
  return packet === undefined
    ? []
    : [
        { kind: "packet", text: packet.tnc2 },
        { kind: "call", text: packet.source },
      ];
});

function toggle(key: string): void {
  open.value = open.value === key ? null : key;
}
</script>

<template>
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
      <template v-for="row in rows" :key="keyOf(row)">
        <tr
          class="packet-row copysource"
          :class="{ selected: open === keyOf(row), out: row.direction === 'out' }"
          tabindex="0"
          :data-key="keyOf(row)"
          v-on="copy.on.value"
          @click="copy.unlessHeld(() => toggle(keyOf(row)))"
          @keydown.enter="toggle(keyOf(row))"
        >
          <td class="mono nowrap time">{{ clockText(row.heard_at) }}</td>
          <td class="dir" :class="row.direction">{{ t(`packets.dir.${row.direction}`) }}</td>
          <td class="via" :class="{ internet: row.via === 'is' }" :title="packetTitle(row.via)">
            <TagMark :tone="packetTone(row.via)">{{ packetLabel(row.via) }}</TagMark>
          </td>
          <td class="mono wrap line">{{ row.tnc2 }}</td>
          <td class="muted route-cell"><RouteText :text="routeWords(row.route)" /></td>
          <td class="wrap summary">{{ row.summary }}<slot name="note" :row="row" /></td>
        </tr>
        <tr v-if="open === keyOf(row)" class="detail">
          <td colspan="6">
            <PacketDetail :row="row" />
          </td>
        </tr>
      </template>
      <tr v-if="rows.length === 0">
        <td colspan="6" class="empty">{{ empty }}</td>
      </tr>
    </tbody>
  </table>
  <CopyMenu v-if="copy.menu.value" :key="copy.key.value" v-bind="copy.menu.value" @close="copy.close()" />
</template>
