<script setup lang="ts">
// One Nearby list as a short table: symbol, call with the reason it belongs to this list,
// distance and bearing arrow. A click or Enter does what a click on a Stations row does (select,
// open the card, fly to it; Ctrl adds a card). A call only heard repeating has no packet of its
// own and is not a button. Right-click copies the call (CopyMenu).
import BearingArrow from "@/components/BearingArrow.vue";
import CopyMenu from "@/components/CopyMenu.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import { useCopyMenu } from "@/composables/useCopyMenu";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import { timedOut } from "@/lib/aging";
import { bearingTitle } from "@/lib/format";
import type { NearbyItem } from "@/lib/nearby";
import { rowSymbolName } from "@/lib/stations";
import { distanceText, distanceUnit } from "@/lib/units";

const props = defineProps<{
  items: readonly NearbyItem[];
  selected: string | null;
  others?: readonly string[];
  label: string;
}>();
const emit = defineEmits<{ select: [call: string, multi?: boolean] }>();
const { now, aging } = useDaemonContext();

const isOpen = (call: string): boolean => call === props.selected || (props.others ?? []).includes(call);
/** Ctrl (Cmd on a Mac) held: the card is added to the open ones, or closed when open. */
const withKey = (event: MouseEvent | KeyboardEvent): boolean => event.ctrlKey || event.metaKey;
/** The copy menu of a row: its call. */
const copy = useCopyMenu((row) =>
  row.dataset["call"] === undefined ? [] : [{ kind: "call", text: row.dataset["call"] }],
);
</script>

<template>
  <table class="grid nearby" :aria-label="label">
    <thead>
      <tr>
        <th></th>
        <th>{{ t("station.table.call") }}</th>
        <th>{{ t("nearby.details") }}</th>
        <th class="num">{{ distanceUnit() }}</th>
        <th>
          <span class="sr-only">{{ t("station.table.bearing") }}</span>
        </th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="item in items"
        :key="item.call"
        :class="{
          selected: isOpen(item.call),
          timedout: item.row !== null && timedOut(aging, item.row, now),
          inert: item.row === null,
        }"
        :aria-selected="item.row === null ? undefined : isOpen(item.call)"
        :tabindex="item.row === null ? undefined : 0"
        class="copysource"
        :data-call="item.call"
        v-on="copy.on.value"
        @click="item.row !== null && copy.unlessHeld(() => emit('select', item.call, withKey($event)))"
        @keydown.enter="item.row !== null && emit('select', item.call, withKey($event))"
      >
        <td class="symbol" :title="item.row === null ? undefined : rowSymbolName(item.row)">
          <SymbolIcon v-if="item.row !== null" :table="item.row.symbol_table" :code="item.row.symbol_code" :size="18" />
        </td>
        <td class="mono strong call">{{ item.call }}</td>
        <td class="what">
          <span v-for="(line, i) in item.lines" :key="i" class="muted line">{{ line }}</span>
        </td>
        <td class="num">{{ distanceText(item.row?.distance_km ?? null) }}</td>
        <td class="bearing" :title="bearingTitle(item.row?.bearing_deg ?? null)">
          <BearingArrow v-if="item.row?.bearing_deg != null" :deg="item.row.bearing_deg" />
          <span v-if="item.row?.bearing_deg != null" class="sr-only">{{ bearingTitle(item.row.bearing_deg) }}</span>
        </td>
      </tr>
    </tbody>
  </table>
  <CopyMenu v-if="copy.menu.value" :key="copy.key.value" v-bind="copy.menu.value" @close="copy.close()" />
</template>
