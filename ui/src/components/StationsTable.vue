<script setup lang="ts">
// The stations heard, as a table: call, symbol, distance, bearing, how long ago it was heard and when its position was, the current temperature of a weather station ("wx"), when it was last heard direct and the share of its packets that came direct ("5 min, 40 %"), packets, path. A column is sorted by a click on its head (again to
// reverse), a filter box and the toggles "with position only", "direct only" (the stations heard direct at some time) and "hide timed out" narrow it, our own station is always on top, the selected row is marked and a click on a row selects the station
// (the map flies to it). A station past its timeout is off the map: its row is dim and says "timed out" in the Position column.
import { computed, ref } from "vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import { usePersistedFlag } from "@/composables/usePersisted";
import { timedOut, type Aging } from "@/lib/aging";
import { ageText, bearingText, distanceText, pathText } from "@/lib/format";
import { directText } from "@/lib/routes";
import { tempShort } from "@/lib/weather";
import { firstDirection, listStations, type Sort, type SortKey } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";

const props = defineProps<{ stations: ReadonlyMap<string, StationRow>; selected: string | null; now: number; aging: Aging }>();
const emit = defineEmits<{ select: [call: string] }>();

const COLUMNS: { key: SortKey | null; title: string; numeric?: boolean }[] = [
  { key: "call", title: "Call" },
  { key: null, title: "" },
  { key: "distance_km", title: "km", numeric: true },
  { key: "bearing_deg", title: "Brg", numeric: true },
  { key: "last_heard", title: "Heard", numeric: true },
  { key: "last_position_at", title: "Position", numeric: true },
  { key: "last_direct_at", title: "Direct", numeric: true },
  { key: "temp_c", title: "wx", numeric: true },
  { key: "packets", title: "Pkts", numeric: true },
  { key: "last_path", title: "Path" },
];

const filter = ref("");
const withPositionOnly = ref(false);
const sort = ref<Sort>({ key: "last_heard", dir: -1 });
const hideTimedOut = usePersistedFlag("hidetimedout", ["on", "off"], false);
const directOnly = usePersistedFlag("directonly", ["on", "off"], false);

const isTimedOut = (row: StationRow): boolean => timedOut(props.aging, row, props.now);
const rows = computed(() =>
  listStations(props.stations.values(), {
    filter: filter.value,
    withPositionOnly: withPositionOnly.value,
    directOnly: directOnly.value,
    hideTimedOut: hideTimedOut.value,
    timedOut: isTimedOut,
    sort: sort.value,
  }),
);

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
  <div class="tablepane">
    <div class="toolbar">
      <input v-model="filter" class="input grow" type="search" placeholder="Filter" title="Call, symbol, comment, path" aria-label="Filter the stations" />
      <label class="check"><input v-model="withPositionOnly" type="checkbox" /> with position only</label>
      <label class="check"><input v-model="hideTimedOut" type="checkbox" /> hide timed out</label>
      <label class="check"><input v-model="directOnly" type="checkbox" /> direct only</label>
    </div>
    <div class="scroll">
      <table class="grid">
        <thead>
          <tr>
            <th v-for="c in COLUMNS" :key="c.title" :class="{ num: c.numeric, sortable: c.key !== null }" :aria-sort="ariaSort(c.key)">
              <button v-if="c.key" type="button" class="headbtn" @click="sortBy(c.key)">
                {{ c.title }}<span v-if="sort.key === c.key" aria-hidden="true">{{ sort.dir === 1 ? " ▲" : " ▼" }}</span>
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.call"
            :class="{ selected: row.call === selected, me: row.is_me, own: row.own, timedout: isTimedOut(row) }"
            :aria-selected="row.call === selected"
            tabindex="0"
            @click="emit('select', row.call)"
            @keydown.enter="emit('select', row.call)"
          >
            <td class="mono strong call">{{ row.call }}</td>
            <td><SymbolIcon :table="row.symbol_table" :code="row.symbol_code" :size="18" /></td>
            <td class="num">{{ distanceText(row.distance_km) }}</td>
            <td class="num">{{ bearingText(row.bearing_deg) }}</td>
            <td class="num">{{ ageText(row.last_heard, now) }}</td>
            <td class="num">{{ ageText(row.last_position_at, now) }}<span v-if="isTimedOut(row)" class="timedword"> timed out</span></td>
            <td class="num">{{ directText(row, now) }}</td>
            <td class="num" :title="row.weather_at ? `${ageText(row.weather_at, now)} ago` : undefined">{{ tempShort(row) }}</td>
            <td class="num">{{ row.packets }}</td>
            <td class="mono path">{{ pathText(row.last_path) }}</td>
          </tr>
          <tr v-if="rows.length === 0">
            <td :colspan="COLUMNS.length" class="empty">{{ stations.size === 0 ? "No station heard yet." : "No station matches." }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="foot muted">{{ rows.length }} of {{ stations.size }} stations</div>
  </div>
</template>
