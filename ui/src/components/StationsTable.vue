<script setup lang="ts">
// The stations heard, as a short table that fits the panel: symbol; call (with a check mark for
// a station heard direct); how it was heard (one tag per radio by name, "iGate" or "Internet";
// two radios at most, one in a narrow table, and "+n" for the rest, whose title lists them with
// times; lib/channels.ts); distance; bearing as a small arrow (north up, "NE, 47°" as its
// title); and when it was last heard (the newest of anything it sent; the full time is the
// title). A click on a column head sorts, again reverses. The filter box (StationsFilters)
// narrows the rows, our own station is always on top, and the selected row is marked. A click
// on a row selects the station (the map flies to it; with Ctrl it adds a card). The click,
// Enter, or Up, Down, Home and End (useRowKeys) also show the station in the panel at the
// bottom of the tab (StationPanel, composables/useStationPanel.ts); its cross or Esc closes it
// with focus back on the row. Every row is one line high, so nothing in the list opens or grows.
// When the filter text is a call no station has been heard under (not ours, not the email
// gateway), a "Message OH2XYZ" button under the empty result writes to it. A timed-out
// station is off the map: its row is dim and says "timed out" after the time. Under the list
// are the count and Forget all (asks twice, 5 s; has an (i)), which removes every heard
// station with its packets and keeps ours. At the right end of a row are a message button and
// a trash can that forgets the station (asks twice, armed together with the panel's Forget);
// clicking them does not select the row. A right-click or long press opens a short menu where
// the pointer is (StationMenu). A station with an alert has a quiet bell after its call
// (AlertBell; every row reserves its place).
import TagMark from "@/components/TagMark.vue";
import TwoWords from "@/components/TwoWords.vue";
import { computed, ref } from "vue";
import AlertBell from "@/components/AlertBell.vue";
import BearingArrow from "@/components/BearingArrow.vue";
import DirectMark from "@/components/DirectMark.vue";
import IconButton from "@/components/IconButton.vue";
import InfoTip from "@/components/InfoTip.vue";
import MessageGlyph from "@/components/MessageGlyph.vue";
import StationMenu from "@/components/StationMenu.vue";
import StationPanel from "@/components/StationPanel.vue";
import StationsFilters from "@/components/StationsFilters.vue";
import TabHelp from "@/components/TabHelp.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useElementWidth } from "@/composables/useElementWidth";
import { useRadios } from "@/composables/useRadios";
import { useRowKeys } from "@/composables/useRowKeys";
import { useRowMenu } from "@/composables/useRowMenu";
import { useStationPanel } from "@/composables/useStationPanel";
import { usePersistedFlag } from "@/composables/usePersisted";
import { useSure } from "@/composables/useSure";
import { t } from "@/i18n";
import { timedOut } from "@/lib/aging";
import { normalizeCall, validCall } from "@/lib/calls";
import { heardTags, internetOnly } from "@/lib/channels";
import { ageText, bearingTitle, dateTimeText, distanceText } from "@/lib/format";
import { isGateway } from "@/lib/messages";
import { receivedFrom } from "@/lib/qru";
import { STATIONS_TWO_RADIOS } from "@/lib/layout";
import { heardDirect } from "@/lib/routes";
import { canForget, canMessage, firstDirection, listStations, stationRowId, rowSymbolName, type QueryKind, type Sort, type SortKey } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{
    selected: string | null;
    others?: readonly string[];
  }>(),
  { others: () => [] },
);
const { stations, now, aging, call: ownCall, send, qru, prefs } = useDaemonContext();
const radios = useRadios();
const root = ref<HTMLElement | null>(null);
const width = useElementWidth(root);
/** The table is narrower than STATIONS_TWO_RADIOS (lib/layout.ts); 0 until measured: not narrow. */
const narrow = computed(() => width.value > 0 && width.value < STATIONS_TWO_RADIOS);
/** Radios shown as tags in "Heard on": two, or one in a narrow table (names may be long); "+n"
 * stands for the rest. */
const radioRoom = computed(() => (narrow.value ? 1 : undefined));
/** Objects that answered a local info request, with the server that sent each (Local info tag). */
const localInfo = computed(() => receivedFrom(qru.value?.servers ?? []));
const emit = defineEmits<{
  select: [call: string, multi?: boolean];
  message: [call: string];
  forget: [call: string];
  ask: [call: string, kind: QueryKind | "custom", text?: string];
  copy: [call: string];
}>();
const isOpen = (call: string): boolean => call === props.selected || props.others.includes(call);
/** Ctrl (Cmd on a Mac) held: the card is added to the open ones, or closed if open. */
const withKey = (event: MouseEvent | KeyboardEvent): boolean => event.ctrlKey || event.metaKey;

/** The columns, with heads in the page's language (rebuilt when it changes). */
const columns = computed<{ key: SortKey | null; title: string; numeric?: boolean }[]>(() => [
  { key: null, title: "" },
  { key: "call", title: t("station.table.call") },
  { key: null, title: t("station.hover.via") },
  { key: "distance_km", title: "km", numeric: true },
  { key: null, title: t("station.table.bearing") },
  { key: "last_heard", title: t("station.field.last_heard"), numeric: true },
  { key: null, title: "" },
]);

/** The row trash can asks twice like the card's Forget: the first press arms it, the second
 * (within 5 s) forgets the station. */
const sure = useSure<string>();
const armed = (call: string): boolean => sure.armed.value === call;
const forget = (call: string): void => sure.press(call, () => emit("forget", call));

/** Forget all asks twice as well ("Really forget all?", 5 s); ours and our objects are kept. */
const sureAll = useSure<"all">();
const anyHeard = computed(() => [...stations.value.values()].some((row) => !row.is_me && !row.own));
const forgetAll = (): void => sureAll.press("all", () => send({ cmd: "forget_all_stations" }));

/** The menu of a row (StationMenu): composables/useRowMenu.ts. */
const { menu, menuRow, press, onContextMenu, closeMenu } = useRowMenu(stations);
/** What the panel and menu buttons do: the parent's events, with Forget asking twice. */
const rowActions = {
  message: (call: string) => emit("message", call),
  ask: (call: string, kind: QueryKind | "custom", text?: string) => emit("ask", call, kind, text),
  show: (call: string) => emit("select", call, false),
  copy: (call: string) => emit("copy", call),
  forget,
};

const filter = ref("");
const sort = ref<Sort>({ key: "last_heard", dir: -1 });
const hideTimedOut = usePersistedFlag("hidetimedout", ["on", "off"], false);
const directOnly = usePersistedFlag("directonly", ["on", "off"], false);
const rfOnly = usePersistedFlag("rfonly", ["on", "off"], false);
const isTimedOut = (row: StationRow): boolean => timedOut(aging.value, row, now.value);
const rows = computed(() =>
  listStations(stations.value.values(), {
    filter: filter.value,
    directOnly: directOnly.value,
    rfOnly: rfOnly.value,
    hideTimedOut: hideTimedOut.value,
    timedOut: isTimedOut,
    sort: sort.value,
  }),
);
const calls = (): string[] => rows.value.map((row) => row.call);

/** The station panel at the bottom of the tab (StationPanel): composables/useStationPanel.ts. */
const panel = useStationPanel(calls);
const panelRow = computed(() => (panel.open.value === null ? undefined : stations.value.get(panel.open.value)));
/** A click or Enter selects the row and shows it in the panel; with Ctrl it adds the card and
 * leaves the panel alone. A click ending a long press is ignored. */
function onRowClick(event: MouseEvent | KeyboardEvent, call: string): void {
  if (event instanceof MouseEvent && press.swallowClick()) return;
  emit("select", call, withKey(event));
  if (!withKey(event)) panel.show(call);
}
/** Up, Down, Home and End select the next row, and show it in the panel. */
const onRowKey = useRowKeys({
  calls,
  select: (call, multi) => {
    emit("select", call, multi);
    if (!multi) panel.show(call);
  },
});

/** The filter text is a call no station has been heard under (not our own, not the email
 * gateway, which has its own tab): a button writes to it anyway. */
const strangerCall = computed(() => {
  const typed = normalizeCall(filter.value);
  const ours = ownCall.value ? normalizeCall(ownCall.value) : "";
  return rows.value.every((row) => row.is_me) && validCall(typed) && !isGateway(typed) && typed !== ours ? typed : null;
});

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
  <div ref="root" class="tablepane">
    <TabHelp :label="t('station.table.about_label')" picture="channels">
      <span class="info-line">{{ t("station.table.about1") }}</span>
      <span class="info-line">{{ t("station.table.about2") }}</span>
    </TabHelp>
    <StationsFilters v-model:filter="filter" v-model:hide-timed-out="hideTimedOut" v-model:direct-only="directOnly" v-model:rf-only="rfOnly" />
    <div class="scroll">
      <table class="grid stations">
        <thead>
          <tr>
            <th v-for="(c, i) in columns" :key="i" :class="{ num: c.numeric, sortable: c.key !== null }" :aria-sort="ariaSort(c.key)">
              <button v-if="c.key" type="button" class="headbtn" @click="sortBy(c.key)">
                {{ c.title }}<span class="sortmark" aria-hidden="true">{{ sort.key === c.key ? (sort.dir === 1 ? "▲" : "▼") : "" }}</span>
              </button>
              <span v-else-if="c.title" class="sr-only">{{ c.title }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :id="stationRowId(row.call)"
            :key="row.call"
            :class="{ selected: isOpen(row.call), me: row.is_me, own: row.own, timedout: isTimedOut(row), internetonly: internetOnly(row) }"
            :aria-selected="isOpen(row.call)"
            tabindex="0"
            :data-call="row.call"
            @click="onRowClick($event, row.call)"
            @keydown.enter="onRowClick($event, row.call)"
            @keydown="onRowKey($event, row.call)"
            @contextmenu="onContextMenu($event, row.call)"
            @pointerdown="press.down"
            @pointermove="press.move"
            @pointerup="press.up"
            @pointercancel="press.cancel"
          >
            <td class="symbol" :title="rowSymbolName(row)"><SymbolIcon :table="row.symbol_table" :code="row.symbol_code" :size="18" /></td>
            <td class="mono strong call">
              <span class="callname">{{ row.call }}</span
              ><AlertBell :alert="prefs.alerts.value.get(row.call)" /><DirectMark v-if="heardDirect(row)" />
            </td>
            <td class="heard">
              <TagMark v-for="tag in heardTags(row, radios.all.value, now, radioRoom)" :key="tag.key" :tone="tag.tone" class="via" :title="tag.title"
                >{{ tag.label }}<span v-if="tag.key === 'more'" class="sr-only"> {{ tag.title }}</span></TagMark
              >
              <TagMark
                v-if="localInfo.has(row.call)"
                tone="neutral"
                class="via"
                :title="t('channel.title.local_info', { server: localInfo.get(row.call) ?? '' })"
                >{{ t("objects.qru") }}</TagMark
              >
            </td>
            <td class="num">{{ distanceText(row.distance_km) }}</td>
            <td class="bearing" :title="bearingTitle(row.bearing_deg)">
              <BearingArrow v-if="row.bearing_deg !== null" :deg="row.bearing_deg" />
              <span v-if="row.bearing_deg !== null" class="sr-only">{{ bearingTitle(row.bearing_deg) }}</span>
            </td>
            <td class="num" :title="dateTimeText(row.last_heard)">
              {{ ageText(row.last_heard, now) }}<span v-if="isTimedOut(row)" class="timedword">{{ ` ${t("station.timed_out")}` }}</span>
            </td>
            <td class="actions" @click.stop @keydown.enter.stop>
              <IconButton
                v-if="canMessage(row)"
                kind="message"
                :label="t('station.table.message_call', { call: row.call })"
                :title="t('station.table.message_call', { call: row.call })"
                @click="emit('message', row.call)"
              />
              <IconButton
                v-if="canForget(row)"
                kind="delete"
                class="forgetbtn"
                :armed="armed(row.call)"
                :label="armed(row.call) ? t('station.table.forget_sure_call', { call: row.call }) : t('station.table.forget_call', { call: row.call })"
                :title="t('station.table.forget_call', { call: row.call })"
                @click="forget(row.call)"
              />
            </td>
          </tr>
          <tr v-if="rows.length === 0">
            <td :colspan="columns.length" class="empty">{{ stations.size === 0 ? t("station.table.none_yet") : t("station.table.none_match") }}</td>
          </tr>
          <tr v-if="strangerCall !== null" class="stranger">
            <td :colspan="columns.length" class="empty">
              <button type="button" class="btn primary msgbtn" @click="emit('message', strangerCall)">
                <MessageGlyph :size="14" />
                {{ t("station.table.message_call", { call: strangerCall }) }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <StationMenu
      v-if="menu && menuRow"
      :key="menu.n"
      :row="menuRow"
      :x="menu.x"
      :y="menu.y"
      :trigger="menu.trigger"
      @show="rowActions.show"
      @copy="rowActions.copy"
      @close="closeMenu"
    />
    <div class="foot footbar muted">
      <span class="footcount">{{ t("station.table.count", { shown: rows.length, n: stations.size }) }}</span>
      <span class="footaction">
        <button type="button" class="btn forgetall" :class="{ danger: sureAll.armed.value !== null }" :disabled="!anyHeard" @click="forgetAll">
          <TwoWords :second="sureAll.armed.value !== null">
            <template #first>{{ t("station.table.forget_all") }}</template>
            <template #second>{{ t("station.table.forget_all_sure") }}</template>
          </TwoWords>
        </button>
        <InfoTip :label="t('station.table.forget_all_label')">
          <span class="info-line">{{ t("station.table.forget_tip") }}</span>
        </InfoTip>
      </span>
    </div>
    <StationPanel v-if="panelRow" :key="panelRow.call" :row="panelRow" :armed="armed(panelRow.call)" v-on="rowActions" @close="panel.close" />
  </div>
</template>
