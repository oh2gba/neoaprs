<script setup lang="ts">
// The stations heard, as a short table that fits the panel: the symbol, the call (a green check mark after it for a station heard direct, and under it in small quiet letters how it was heard: RF, iGate, Internet, or two
// joined; lib/channels.ts), the distance from us, the bearing as a small arrow (north up; "NE, 47°" is its hover title) and when the station was last heard at all (the newest of anything it sent, with the full time as the
// hover title). A column is sorted by a click on its head (again to reverse), the group box over it (StationsFilters: a filter box and the toggles "direct only", "heard on RF only" and "hide timed out", and "On map for")
// narrows it, our own station is always on top, the selected row is marked and a click on a row selects the station (the map flies to it; with Ctrl it adds a card). The click (or Enter, or Up, Down, Home and End, which
// select the next row: useRowKeys) also shows the station in the station panel fixed at the bottom of the tab, as the box of every tab is (StationPanel: its actions, its traffic as the lines of the Packets tab, the route
// of messages to it and "Alert me when…"; composables/useStationPanel.ts); its cross or Esc closes it with the focus back on the row. Nothing in the list opens or grows: every row is one line high. When the filter text is a
// call that no station has been heard under (not ours, not the email gateway), a button "Message OH2XYZ" under the empty result writes to it all the same. A station past its timeout is off the map: its row is dim and
// says "timed out" after the time it was heard. Under the list are the count and Forget all, which asks twice ("Really forget all?", 5 s) and has its (i): it removes every station heard with its packets and keeps ours. At
// the right end of a row are two small buttons, as on the card: a speech bubble that opens the conversation with the station ("Message OH2XYZ") and a trash can that forgets it ("Forget OH2XYZ"; it asks twice like the
// card's, "sure?" for 5 s; armed together with the panel's Forget); a click on them does not select the row. A right-click on a row (a long press on a touch screen) opens a short menu where the pointer is (StationMenu:
// Copy call, Show on map, QRZ page), as the Packets tab's copies. A station with an alert set has a small quiet bell after its call (AlertBell: every row has its place, so that nothing moves).
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
import { useRowKeys } from "@/composables/useRowKeys";
import { useRowMenu } from "@/composables/useRowMenu";
import { useStationPanel } from "@/composables/useStationPanel";
import { usePersistedFlag } from "@/composables/usePersisted";
import { useSure } from "@/composables/useSure";
import { t } from "@/i18n";
import { timedOut } from "@/lib/aging";
import { normalizeCall, validCall } from "@/lib/calls";
import { channelTags, internetOnly } from "@/lib/channels";
import { ageText, bearingTitle, dateTimeText, distanceText } from "@/lib/format";
import { isGateway } from "@/lib/messages";
import { receivedFrom } from "@/lib/qru";
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
/** The objects that came in answer to a request for local info, with the server that sent each (the Local info tag). */
const localInfo = computed(() => receivedFrom(qru.value?.servers ?? []));
const emit = defineEmits<{
  select: [call: string, multi?: boolean];
  message: [call: string];
  forget: [call: string];
  ask: [call: string, kind: QueryKind | "custom", text?: string];
  copy: [call: string];
}>();
const isOpen = (call: string): boolean => call === props.selected || props.others.includes(call);
/** Ctrl (Cmd on a Mac) held: the station's card is added to the open ones, or closed when it is open. */
const withKey = (event: MouseEvent | KeyboardEvent): boolean => event.ctrlKey || event.metaKey;

/** The columns, with the head of each in the page's language (made again when the language changes). */
const columns = computed<{ key: SortKey | null; title: string; numeric?: boolean }[]>(() => [
  { key: null, title: "" },
  { key: "call", title: t("station.table.call") },
  { key: null, title: t("station.hover.via") },
  { key: "distance_km", title: "km", numeric: true },
  { key: null, title: t("station.table.bearing") },
  { key: "last_heard", title: t("station.field.last_heard"), numeric: true },
  { key: null, title: "" },
]);

/** The trash can of a row asks twice, as the card's Forget does: the first press arms it ("sure?"), the second (within 5 s) forgets the station. */
const sure = useSure<string>();
const armed = (call: string): boolean => sure.armed.value === call;
const forget = (call: string): void => sure.press(call, () => emit("forget", call));

/** Forget all (at the foot) asks twice as well: the first press arms it ("Really forget all?"), the second (within 5 s) sends the command. It is there to press while some station is heard (ours and our objects are not forgotten). */
const sureAll = useSure<"all">();
const anyHeard = computed(() => [...stations.value.values()].some((row) => !row.is_me && !row.own));
const forgetAll = (): void => sureAll.press("all", () => send({ cmd: "forget_all_stations" }));

/** The menu of a row (StationMenu): composables/useRowMenu.ts. */
const { menu, menuRow, press, onContextMenu, closeMenu } = useRowMenu(stations);
/** What the buttons of the panel and of the menu do: the parent's events, and Forget asking twice. */
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
/** A click on a row (or Enter) selects it and shows it in the panel; with Ctrl it adds the card and leaves the panel as it is. Not the click of the finger that was lifted after a long press. */
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

/** The filter text is a call that no station has been heard under (our own row is always listed, so it does not count; and the text is not ours, nor the email gateway's: that has its own tab): a button writes to it all the same, to a station that has not been heard yet. */
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
  <div class="tablepane">
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
              <TagMark v-for="tag in channelTags(row)" :key="tag.channel" :tone="tag.tone" class="via" :title="tag.title">{{ tag.label }}</TagMark>
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
