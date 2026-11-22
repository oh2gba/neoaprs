<script setup lang="ts">
// The packets as lines, newest first, shared by the Packets tab and a station's traffic panel. Each
// line shows time, direction, channel, the TNC2 text, the route and the daemon's summary. A click
// or Enter opens PacketDetail under the line; a right-click offers to copy the line and call. With
// `stacked` each packet is one block and the header row is for screen readers only.
import TagMark from "@/components/TagMark.vue";
import { ref } from "vue";
import CopyMenu from "@/components/CopyMenu.vue";
import PacketDetail from "@/components/PacketDetail.vue";
import RouteText from "@/components/RouteText.vue";
import { useCopyMenu } from "@/composables/useCopyMenu";
import { t } from "@/i18n";
import { packetTag } from "@/lib/channels";
import { useRadios } from "@/composables/useRadios";
import { clockText } from "@/lib/format";
import { summaryText } from "@/lib/packetview";
import { routeWords } from "@/lib/routes";
import type { PacketRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ rows: readonly PacketRow[]; stacked: boolean; empty: string; keyOf?: (row: PacketRow) => string }>(), {
  keyOf: (row: PacketRow) => String(row.id),
});
const radios = useRadios();
const tagOf = (row: PacketRow) => packetTag(row, radios.all.value);
defineSlots<{ note?: (props: { row: PacketRow }) => unknown }>();

const open = ref<string | null>(null);
/** The copy menu of a line: the packet as monitor text, and the call that sent it. */
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
          <td class="via" :class="{ internet: row.via === 'is' }" :title="tagOf(row)?.title">
            <TagMark v-if="tagOf(row)" :tone="tagOf(row)?.tone ?? 'neutral'">{{ tagOf(row)?.label }}</TagMark>
          </td>
          <td class="mono wrap line">{{ row.tnc2 }}</td>
          <td class="muted route-cell"><RouteText :text="routeWords(row.route)" /></td>
          <td class="wrap summary">{{ summaryText(row) }}<slot name="note" :row="row" /></td>
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
