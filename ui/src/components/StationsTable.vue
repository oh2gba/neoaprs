<script setup lang="ts">
// The stations heard, as a short table that fits the panel: the symbol, the call (a green check mark after it for a station heard direct, and under it in small quiet letters how it was heard: RF, iGate, Internet, or two joined; lib/channels.ts), the distance from us, the bearing as a small arrow (north up; "NE, 47°" is its hover title) and when the station was last heard at all (the newest of anything it sent, with the full time as the hover title); the rest of what is known of a station (when its position was, how its packets reach us, the path, the packets, the weather) is on its card, a click away. A column is sorted by a click on its head (again to
// reverse), a filter box and the toggles "direct only" (the stations heard direct at some time), "heard on RF only" (leaves out the stations known from the internet alone; it is there only once a station has been received over the internet) and "hide timed out" narrow it, our own station is always on top, the selected row is marked and a click on a row selects the station
// (the map flies to it; with Ctrl it adds a card). When the filter text is a call that no station has been heard under (not ours, not the email gateway), a button "Message OH2XYZ" under the empty result writes to it all the same. A station past its timeout is off the map: its row is dim and says "timed out" after the time it was heard. At the foot are the count and Forget all, which asks twice ("Really forget all?", 5 s) and has its (i): it removes every station heard with its packets and keeps ours. Every row is one line high. At the right end of a row are two small buttons, as on the card: a speech bubble that opens the conversation with the station ("Message OH2XYZ", where the card has Message) and a trash can that forgets it ("Forget OH2XYZ", where the card has Forget; it asks twice like the card's, "sure?" for 5 s); a click on them does not select the row. Between them is a "..." button, and a right-click on a row (a long press on a touch screen) opens the same menu where the pointer is (StationMenu: Message, the directed queries, Show, "Alert me when…", Copy call, QRZ, Forget). "Alert me when…" opens a small box where the menu was (StationAlertBox); a station with an alert set has a small quiet bell after its call (AlertBell: every row has its place, so that nothing moves).
import TagMark from "@/components/TagMark.vue";
import { computed, ref } from "vue";
import AlertBell from "@/components/AlertBell.vue";
import BearingArrow from "@/components/BearingArrow.vue";
import DirectMark from "@/components/DirectMark.vue";
import IconButton from "@/components/IconButton.vue";
import InfoTip from "@/components/InfoTip.vue";
import MessageGlyph from "@/components/MessageGlyph.vue";
import StationAlertBox from "@/components/StationAlertBox.vue";
import StationMenu from "@/components/StationMenu.vue";
import TabHelp from "@/components/TabHelp.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRowKeys } from "@/composables/useRowKeys";
import { useRowMenu } from "@/composables/useRowMenu";
import { usePersistedFlag } from "@/composables/usePersisted";
import { useSure } from "@/composables/useSure";
import { t } from "@/i18n";
import { STATION_HOURS_KEY, stationHours, timedOut } from "@/lib/aging";
import { normalizeCall, validCall } from "@/lib/calls";
import { anyInternet, channelTags, internetOnly } from "@/lib/channels";
import { ageText, bearingTitle, dateTimeText, distanceText } from "@/lib/format";
import { isGateway } from "@/lib/messages";
import { receivedFrom } from "@/lib/qru";
import { heardDirect } from "@/lib/routes";
import { FIELDS } from "@/lib/settings";
import { canForget, canMessage, firstDirection, listStations, stationRowId, symbolName, type QueryKind, type Sort, type SortKey } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{
    selected: string | null;
    others?: readonly string[];
  }>(),
  { others: () => [] },
);
const { stations, now, aging, call: ownCall, settings, send, qru, prefs, home } = useDaemonContext();
/** The objects that came in answer to a request for local info, with the server that sent each (the Local info tag). */
const localInfo = computed(() => receivedFrom(qru.value?.servers ?? []));
const emit = defineEmits<{
  select: [call: string, multi?: boolean];
  message: [call: string];
  forget: [call: string];
  ask: [call: string, kind: QueryKind];
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

/** The menu of a row (StationMenu) and the box of its "Alert me when…" (StationAlertBox): composables/useRowMenu.ts. */
const { menu, menuRow, alertBox, press, onContextMenu, pressFrom, openFrom, openAlertBox, closeMenu, closeAlertBox } = useRowMenu(stations);
/** A click on a row selects it, except the click of the finger that was lifted after a long press. */
function onRowClick(event: MouseEvent, call: string): void {
  if (press.swallowClick()) return;
  emit("select", call, withKey(event));
}

const onRowKey = useRowKeys({ calls: () => rows.value.map((row) => row.call), select: (call, multi) => emit("select", call, multi) });

const filter = ref("");
const sort = ref<Sort>({ key: "last_heard", dir: -1 });
const hideTimedOut = usePersistedFlag("hidetimedout", ["on", "off"], false);
const directOnly = usePersistedFlag("directonly", ["on", "off"], false);
const rfOnly = usePersistedFlag("rfonly", ["on", "off"], false);
/** The tickbox "heard on RF only" is there once a station has been received over the internet; until then there is nothing for it to leave out. */
const internetKnown = computed(() => anyInternet(stations.value.values()));

/** How long a station stays on the map: the setting of the daemon (the same in every browser), changed at once with an Undo. */
const hours = computed(() =>
  String(stationHours({ [STATION_HOURS_KEY]: settings.draft[STATION_HOURS_KEY] ?? settings.values.value[STATION_HOURS_KEY] ?? "" })),
);
const hourChoices = computed(() => (FIELDS[STATION_HOURS_KEY]?.choices ?? []).map((c) => (typeof c === "string" ? { value: c, label: c } : c)));
function chooseHours(event: Event): void {
  settings.change({ [STATION_HOURS_KEY]: (event.target as HTMLSelectElement).value });
}

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
  <div class="tablepane">
    <TabHelp :label="t('station.table.about_label')" picture="channels">
      <span class="info-line">{{ t("station.table.about1") }}</span>
      <span class="info-line">{{ t("station.table.about2") }}</span>
    </TabHelp>
    <fieldset class="filters">
      <legend>{{ t("station.table.filter") }}</legend>
      <div class="toolbar">
        <input
          v-model="filter"
          class="input filterbox"
          type="search"
          :placeholder="t('station.table.filter_title')"
          :title="t('station.table.filter_title')"
          :aria-label="t('station.table.filter_label')"
          @keydown.esc="clearFilter"
        />
        <div class="toolbar-checks">
          <label class="check"><input v-model="hideTimedOut" type="checkbox" /> {{ t("station.table.hide_timed_out") }}</label>
          <label class="check"><input v-model="directOnly" type="checkbox" /> {{ t("station.table.direct_only") }}</label>
          <label v-if="internetKnown" class="check" :title="t('station.table.rf_only_title')"
            ><input v-model="rfOnly" type="checkbox" /> {{ t("station.table.rf_only") }}</label
          >
          <label class="check onmap"
            >{{ t("station.table.on_map") }}
            <select id="stations-on-map" class="input" :value="hours" @change="chooseHours">
              <option v-for="choice in hourChoices" :key="choice.value" :value="choice.value">{{ choice.label }}</option>
            </select></label
          >
        </div>
      </div>
    </fieldset>
    <div class="scroll">
      <table class="grid stations">
        <thead>
          <tr>
            <th v-for="(c, i) in columns" :key="i" :class="{ num: c.numeric, sortable: c.key !== null }" :aria-sort="ariaSort(c.key)">
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
            :id="stationRowId(row.call)"
            :key="row.call"
            :class="{ selected: isOpen(row.call), me: row.is_me, own: row.own, timedout: isTimedOut(row), internetonly: internetOnly(row) }"
            :aria-selected="isOpen(row.call)"
            tabindex="0"
            :data-call="row.call"
            @click="onRowClick($event, row.call)"
            @keydown.enter="emit('select', row.call, withKey($event))"
            @keydown="onRowKey($event, row.call)"
            @contextmenu="onContextMenu($event, row.call)"
            @pointerdown="press.down"
            @pointermove="press.move"
            @pointerup="press.up"
            @pointercancel="press.cancel"
          >
            <td class="symbol" :title="symbolName(row)"><SymbolIcon :table="row.symbol_table" :code="row.symbol_code" :size="18" /></td>
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
              <IconButton
                kind="more"
                class="morebtn"
                aria-haspopup="menu"
                :aria-expanded="menu?.call === row.call"
                :label="t('station.menu.more', { call: row.call })"
                @pointerdown="pressFrom($event, row.call)"
                @click="openFrom($event, row.call)"
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
      :armed="armed(menu.call)"
      @close="closeMenu"
      @message="emit('message', $event)"
      @ask="(call, kind) => emit('ask', call, kind)"
      @show="emit('select', $event, false)"
      @alert="openAlertBox"
      @copy="emit('copy', $event)"
      @forget="forget"
    />
    <StationAlertBox
      v-if="alertBox"
      :key="alertBox.call"
      :call="alertBox.call"
      :alert="prefs.alerts.value.get(alertBox.call) ?? null"
      :x="alertBox.x"
      :y="alertBox.y"
      :trigger="alertBox.trigger"
      :placed="home !== null"
      @save="prefs.setAlert"
      @close="closeAlertBox"
    />
    <div class="foot footbar muted">
      <span class="footcount">{{ t("station.table.count", { shown: rows.length, n: stations.size }) }}</span>
      <span class="footaction">
        <button type="button" class="btn forgetall" :class="{ danger: sureAll.armed.value !== null }" :disabled="!anyHeard" @click="forgetAll">
          {{ sureAll.armed.value !== null ? t("station.table.forget_all_sure") : t("station.table.forget_all") }}
        </button>
        <InfoTip :label="t('station.table.forget_all_label')">
          <span class="info-line">{{ t("station.table.forget_tip") }}</span>
        </InfoTip>
      </span>
    </div>
  </div>
</template>
