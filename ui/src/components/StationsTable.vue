<script setup lang="ts">
// The stations heard, as a short table that fits the panel: the symbol, the call (a green check mark after it for a station heard direct), the distance from us, the bearing as a small arrow (north up; "NE, 47°" is its hover title) and when the station was last heard at all (the newest of anything it sent, with the full time as the hover title); the rest of what is known of a station (when its position was, how its packets reach us, the path, the packets, the weather) is on its card, a click away. A column is sorted by a click on its head (again to
// reverse), a filter box and the toggles "with position only", "direct only" (the stations heard direct at some time) and "hide timed out" narrow it, our own station is always on top, the selected row is marked and a click on a row selects the station
// (the map flies to it; with Ctrl it adds a card). When the filter text is a call that no station has been heard under (not ours, not the email gateway), a button "Message OH2XYZ" under the empty result writes to it all the same. A station past its timeout is off the map: its row is dim and says "timed out" after the time it was heard. Every row is one line high.
import { computed, ref } from "vue";
import DirectMark from "@/components/DirectMark.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { usePersistedFlag } from "@/composables/usePersisted";
import { timedOut } from "@/lib/aging";
import { normalizeCall, validCall } from "@/lib/calls";
import { ageText, bearingTitle, dateTimeText, distanceText } from "@/lib/format";
import { isGateway } from "@/lib/messages";
import { heardDirect } from "@/lib/routes";
import { firstDirection, listStations, type Sort, type SortKey } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{
    selected: string | null;
    others?: readonly string[];
  }>(),
  { others: () => [] },
);
const { stations, now, aging, call: ownCall } = useDaemonContext();
const emit = defineEmits<{ select: [call: string, multi?: boolean]; message: [call: string] }>();
const isOpen = (call: string): boolean => call === props.selected || props.others.includes(call);
/** Ctrl (Cmd on a Mac) held: the station's card is added to the open ones, or closed when it is open. */
const withKey = (event: MouseEvent | KeyboardEvent): boolean => event.ctrlKey || event.metaKey;

const COLUMNS: { key: SortKey | null; title: string; numeric?: boolean }[] = [
  { key: null, title: "" },
  { key: "call", title: "Call" },
  { key: null, title: "heard direct" },
  { key: "distance_km", title: "km", numeric: true },
  { key: null, title: "bearing" },
  { key: "last_heard", title: "Last heard", numeric: true },
];

const filter = ref("");
const withPositionOnly = ref(false);
const sort = ref<Sort>({ key: "last_heard", dir: -1 });
const hideTimedOut = usePersistedFlag("hidetimedout", ["on", "off"], false);
const directOnly = usePersistedFlag("directonly", ["on", "off"], false);

const isTimedOut = (row: StationRow): boolean => timedOut(aging.value, row, now.value);
const rows = computed(() =>
  listStations(stations.value.values(), {
    filter: filter.value,
    withPositionOnly: withPositionOnly.value,
    directOnly: directOnly.value,
    hideTimedOut: hideTimedOut.value,
    timedOut: isTimedOut,
    sort: sort.value,
  }),
);

/** The filter text is a call that no station has been heard under (our own row is always listed, so it does not count; and the text is not ours, nor the email gateway's: that has its own tab): a button writes to it all the same, to a station that has not been heard yet. */
const strangerCall = computed(() => {
  const typed = normalizeCall(filter.value);
  const ours = ownCall.value ? normalizeCall(ownCall.value) : "";
  return rows.value.every((row) => row.is_me) && validCall(typed) && !isGateway(typed) && typed !== ours ? typed : null;
});

/** Esc in the filter box clears the text; with the box empty it is not taken, and goes on to close the newest card. */
function clearFilter(event: KeyboardEvent): void {
  if (filter.value === "") return;
  filter.value = "";
  event.preventDefault();
}

function sortBy(key: SortKey | null): void {
  if (key === null) return;
  sort.value = sort.value.key === key ? { key, dir: sort.value.dir === 1 ? -1 : 1 } : { key, dir: firstDirection(key) };
}

function ariaSort(key: SortKey | null): "ascending" | "descending" | "none" | undefined {
  if (key === null) return undefined;
  return sort.value.key !== key ? "none" : sort.value.dir === 1 ? "ascending" : "descending";
}
</script>

<template>
  <div class="tablepane capped">
    <div class="toolbar">
      <input
        v-model="filter"
        class="input filterbox"
        type="search"
        placeholder="Filter"
        title="Call, symbol, comment, path"
        aria-label="Filter the stations"
        @keydown.esc="clearFilter"
      />
      <div class="toolbar-checks">
        <label class="check"><input v-model="withPositionOnly" type="checkbox" /> with position only</label>
        <label class="check"><input v-model="hideTimedOut" type="checkbox" /> hide timed out</label>
        <label class="check"><input v-model="directOnly" type="checkbox" /> direct only</label>
      </div>
    </div>
    <div class="scroll">
      <table class="grid stations">
        <thead>
          <tr>
            <th v-for="c in COLUMNS" :key="c.title" :class="{ num: c.numeric, sortable: c.key !== null }" :aria-sort="ariaSort(c.key)">
              <button v-if="c.key" type="button" class="headbtn" @click="sortBy(c.key)">
                {{ c.title }}<span v-if="sort.key === c.key" aria-hidden="true">{{ sort.dir === 1 ? " ▲" : " ▼" }}</span>
              </button>
              <span v-else-if="c.title" class="sr-only">{{ c.title }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.call"
            :class="{ selected: isOpen(row.call), me: row.is_me, own: row.own, timedout: isTimedOut(row) }"
            :aria-selected="isOpen(row.call)"
            tabindex="0"
            @click="emit('select', row.call, withKey($event))"
            @keydown.enter="emit('select', row.call, withKey($event))"
          >
            <td class="symbol" :title="row.symbol_name"><SymbolIcon :table="row.symbol_table" :code="row.symbol_code" :size="18" /></td>
            <td class="mono strong call">{{ row.call }}</td>
            <td class="direct"><DirectMark v-if="heardDirect(row)" /></td>
            <td class="num">{{ distanceText(row.distance_km) }}</td>
            <td class="bearing" :title="bearingTitle(row.bearing_deg)">
              <svg
                v-if="row.bearing_deg !== null"
                class="arrow"
                width="14"
                height="14"
                viewBox="0 0 14 14"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                :style="{ transform: `rotate(${row.bearing_deg}deg)` }"
                aria-hidden="true"
              >
                <path d="M7 12.5V2M3 6l4-4 4 4" />
              </svg>
              <span v-if="row.bearing_deg !== null" class="sr-only">{{ bearingTitle(row.bearing_deg) }}</span>
            </td>
            <td class="num" :title="dateTimeText(row.last_heard)">
              {{ ageText(row.last_heard, now) }}<span v-if="isTimedOut(row)" class="timedword"> timed out</span>
            </td>
          </tr>
          <tr v-if="rows.length === 0">
            <td :colspan="COLUMNS.length" class="empty">{{ stations.size === 0 ? "No station heard yet." : "No station matches." }}</td>
          </tr>
          <tr v-if="strangerCall !== null" class="stranger">
            <td :colspan="COLUMNS.length" class="empty">
              <button type="button" class="btn primary" @click="emit('message', strangerCall)">Message {{ strangerCall }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="foot muted">{{ rows.length }} of {{ stations.size }} stations</div>
  </div>
</template>
