<script setup lang="ts">
// One list of the Nearby tab as a short table, the rows of the Stations table in small: the symbol, the call with the words under it (what makes the station belong to this list), the distance from us and the bearing as a small arrow. A click on a row
// does what a click on a row of the Stations table does (the station is selected, its card opens and the map flies to it; with Ctrl it adds a card), and so does Enter. A row for a call that was only heard repeating, with no packet of its own,
// has nothing to select and is not a button. A station past its timeout (off the map) is dim, as in the Stations table. The distance is empty for a station without a position. A right-click on a row (a long press on a touch screen) offers to copy its call (CopyMenu).
import BearingArrow from "@/components/BearingArrow.vue";
import CopyMenu from "@/components/CopyMenu.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import { useCopyMenu } from "@/composables/useCopyMenu";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import { timedOut } from "@/lib/aging";
import { bearingTitle, distanceText } from "@/lib/format";
import type { NearbyItem } from "@/lib/nearby";
import { rowSymbolName } from "@/lib/stations";

const props = defineProps<{ items: readonly NearbyItem[]; selected: string | null; others?: readonly string[]; label: string }>();
const emit = defineEmits<{ select: [call: string, multi?: boolean] }>();
const { now, aging } = useDaemonContext();

const isOpen = (call: string): boolean => call === props.selected || (props.others ?? []).includes(call);
/** Ctrl (Cmd on a Mac) held: the station's card is added to the open ones, or closed when it is open. */
const withKey = (event: MouseEvent | KeyboardEvent): boolean => event.ctrlKey || event.metaKey;
/** The copy menu of a row: its call. */
const copy = useCopyMenu((row) => (row.dataset["call"] === undefined ? [] : [{ kind: "call", text: row.dataset["call"] }]));
</script>

<template>
  <table class="grid nearby" :aria-label="label">
    <thead>
      <tr>
        <th></th>
        <th>{{ t("station.table.call") }}</th>
        <th>{{ t("nearby.details") }}</th>
        <th class="num">km</th>
        <th>
          <span class="sr-only">{{ t("station.table.bearing") }}</span>
        </th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="item in items"
        :key="item.call"
        :class="{ selected: isOpen(item.call), timedout: item.row !== null && timedOut(aging, item.row, now), inert: item.row === null }"
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
