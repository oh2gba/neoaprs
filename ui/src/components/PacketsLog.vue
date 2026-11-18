<script setup lang="ts">
// The packets as they arrive, newest first, as lines (components/PacketLines.vue: the time, the direction, the channel or the radio, the TNC2 line, the route and what the daemon made of it; a click opens a packet in plain
// facts, a right-click offers to copy its line and its sender's call). A filter box narrows the list, also by the word of its Via (a radio's name where it is named); its text is one for the page (composables/usePacketFilter.ts), so the tab and the Packets card over the map show the same list. Laid out by the width of the tab itself (not of the window: the panel beside the map can be narrow on a wide screen; PACKETS_TABLE,
// lib/layout.ts): the table of columns when it is wide enough, else one block for each packet; the click, the detail and the filter are the same in both.
import { computed, ref } from "vue";
import { useElementWidth } from "@/composables/useElementWidth";
import { PACKETS_TABLE } from "@/lib/layout";
import { t } from "@/i18n";
import PacketLines from "@/components/PacketLines.vue";
import TabHelp from "@/components/TabHelp.vue";
import { usePacketFilter } from "@/composables/usePacketFilter";
import { useRadios } from "@/composables/useRadios";
import { packetTag } from "@/lib/channels";
import { filterPackets, newestFirst } from "@/lib/packets";
import type { PacketRow } from "@/protocol/protocol";

const props = defineProps<{ packets: ReadonlyMap<string, PacketRow> }>();

const root = ref<HTMLElement | null>(null);
const width = useElementWidth(root);
/** The tab is narrower than the table needs (0 until it is measured: the table). */
const stacked = computed(() => width.value > 0 && width.value < PACKETS_TABLE);
const filter = usePacketFilter();

const radios = useRadios();
/** The packets that have the text, by lib/packets.ts, or in the word of their Via tag (the radio's name, iGate, Internet). */
const rows = computed(() => {
  const all = newestFirst(props.packets.values());
  const needle = filter.value.trim().toLowerCase();
  const found = new Set(filterPackets(all, filter.value));
  return needle === "" ? all : all.filter((row) => found.has(row) || (packetTag(row, radios.all.value)?.label.toLowerCase().includes(needle) ?? false));
});
</script>

<template>
  <div ref="root" class="tablepane">
    <TabHelp :label="t('packets.about_label')">
      <span class="info-line">{{ t("packets.about1") }}</span>
      <span class="info-line">{{ t("packets.about2") }}</span>
    </TabHelp>
    <fieldset class="filters">
      <legend>{{ t("packets.filter") }}</legend>
      <div class="toolbar">
        <input
          v-model="filter"
          class="input grow"
          type="search"
          :placeholder="t('packets.filter_title')"
          :title="t('packets.filter_title')"
          :aria-label="t('packets.filter_label')"
        />
      </div>
    </fieldset>
    <div class="scroll">
      <PacketLines :rows="rows" :stacked="stacked" :empty="packets.size === 0 ? t('packets.none_yet') : t('packets.none_match')" />
    </div>
    <div class="foot muted">{{ t("packets.count", { shown: rows.length, n: packets.size }) }}</div>
  </div>
</template>
