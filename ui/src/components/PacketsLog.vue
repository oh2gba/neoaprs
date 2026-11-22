<script setup lang="ts">
// The packets, newest first, as lines (PacketLines). A filter box narrows the list; the filter text
// is shared with the Packets card (usePacketFilter). The layout follows the width of the tab
// itself: a table when wide enough, else one block per packet.
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
/** Whether the tab is narrower than the table needs (false until measured). */
const stacked = computed(() => width.value > 0 && width.value < PACKETS_TABLE);
const filter = usePacketFilter();

const radios = useRadios();
/** The packets that match the filter text, or the word of their Via tag. */
const rows = computed(() => {
  const all = newestFirst(props.packets.values());
  const needle = filter.value.trim().toLowerCase();
  const found = new Set(filterPackets(all, filter.value));
  return needle === ""
    ? all
    : all.filter(
        (row) => found.has(row) || (packetTag(row, radios.all.value)?.label.toLowerCase().includes(needle) ?? false),
      );
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
      <PacketLines
        :rows="rows"
        :stacked="stacked"
        :empty="packets.size === 0 ? t('packets.none_yet') : t('packets.none_match')"
      />
    </div>
    <div class="foot muted">{{ t("packets.count", { shown: rows.length, n: packets.size }) }}</div>
  </div>
</template>
