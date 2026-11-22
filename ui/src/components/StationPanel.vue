<script setup lang="ts">
// The panel at the bottom of the Stations tab for the selected station: call as legend, a close
// button (Esc too), a fixed height so the list above never moves, and scrolling inside.
// Contents, in order: Message and the directed queries (lib/stations.ts `panelItems`) with the
// own query below (StationQuery); Show on map, Copy call, QRZ and Forget (asks twice); the
// station's traffic (StationTraffic); route settings (StationPrefs) and alerts
// (StationAlertChoices) in group boxes. Queries go out on the station's radio and are off while
// its link is down; Trace the route is greyed while that radio carries no path. Own station
// and objects have only the actions that apply. Buttons emit events; the parent acts.
import { computed } from "vue";
import IconButton from "@/components/IconButton.vue";
import TwoWords from "@/components/TwoWords.vue";
import MessageGlyph from "@/components/MessageGlyph.vue";
import StationAlertChoices from "@/components/StationAlertChoices.vue";
import StationPrefs from "@/components/StationPrefs.vue";
import StationQuery from "@/components/StationQuery.vue";
import StationTraffic from "@/components/StationTraffic.vue";
import { useAlertDraft } from "@/composables/useAlertDraft";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useReceiveOnly } from "@/composables/useReceiveOnly";
import { useStationRadio } from "@/composables/useStationRadio";
import { t } from "@/i18n";
import { qrzUrl } from "@/lib/calls";
import { rxOnlyReason } from "@/lib/compose";
import { canAlert } from "@/lib/stationalert";
import { canMessage, itemLabel, itemQuery, panelItems, talksTo, type PanelItem, type QueryKind } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";

const props = defineProps<{ row: StationRow; armed: boolean }>();
const emit = defineEmits<{
  close: [];
  message: [call: string];
  ask: [call: string, kind: QueryKind | "custom", text?: string];
  show: [call: string];
  copy: [call: string];
  forget: [call: string];
}>();
const { prefs, heardPaths, home } = useDaemonContext();
const {
  offline,
  shown,
  paths,
  fallback,
  choices,
  choice,
  auto,
  fixed,
  pathShown,
  pathless,
  reply,
  setPath,
  clearPath,
  choose: chooseRadio,
} = useStationRadio(
  () => props.row.call,
  () => props.row,
);
const rxOnly = useReceiveOnly();

/** The query that asks for a path, which a radio without paths cannot carry. */
const PATH_QUERY: PanelItem = "ask_trace";
const items = computed(() => panelItems(props.row).filter((item) => item !== PATH_QUERY || pathShown.value));
/** Why a query is off: RX only, radio not connected or without paths; undefined if allowed. */
function blocked(item: PanelItem): string | undefined {
  if (item === "message") return undefined;
  if (rxOnly.value) return rxOnlyReason();
  return offline.value ?? (item === PATH_QUERY ? pathless.value : undefined);
}
const talk = computed(() => items.value.filter(talksTo));
const rest = computed(() => items.value.filter((item) => !talksTo(item)));
const qrz = computed(() => qrzUrl(props.row.call) ?? undefined);

const { onAir, near, km, direct, kmOk, alert } = useAlertDraft(() => prefs.alerts.value.get(props.row.call) ?? null);
function saveAlert(): void {
  const value = alert();
  if (value !== null) prefs.setAlert(props.row.call, value);
}

function choose(item: PanelItem): void {
  const call = props.row.call;
  const kind = itemQuery(item);
  if (kind !== null) emit("ask", call, kind);
  else if (item === "message") emit("message", call);
  else if (item === "show") emit("show", call);
  else if (item === "copy") emit("copy", call);
  else if (item === "forget") emit("forget", call);
}

function onEsc(event: KeyboardEvent): void {
  event.preventDefault();
  emit("close");
}
</script>

<template>
  <section
    class="composebar boxed stationpanel"
    :aria-label="t('station.row.label', { call: row.call })"
    @keydown.esc="onEsc"
  >
    <fieldset class="composebox stationpanel-box">
      <legend class="stationpanel-legend">
        <span class="mono">{{ row.call }}</span>
        <IconButton
          kind="close"
          :label="t('station.panel.close')"
          :title="t('station.panel.close')"
          @click="emit('close')"
        />
      </legend>
      <div class="stationpanel-body">
        <div v-if="talk.length > 0" class="stationpanel-line">
          <button
            v-for="item in talk"
            :key="item"
            type="button"
            class="btn"
            :class="{ primary: item === 'message', msgbtn: item === 'message' }"
            :disabled="blocked(item) !== undefined"
            :title="blocked(item) ?? (item === 'ask_weather' ? t('station.menu.ask_weather_title') : undefined)"
            :data-item="item"
            @click="choose(item)"
          >
            <MessageGlyph v-if="item === 'message'" :size="14" />{{ itemLabel(item, row, false) }}
          </button>
        </div>
        <StationQuery
          v-if="canMessage(row)"
          :call="row.call"
          :offline="offline"
          @ask="(text) => emit('ask', row.call, 'custom', text)"
        />
        <div class="stationpanel-line">
          <template v-for="item in rest" :key="item">
            <a
              v-if="item === 'qrz'"
              class="btn"
              :href="qrz"
              target="_blank"
              rel="noopener noreferrer"
              :data-item="item"
              >{{ itemLabel(item, row, false) }}</a
            >
            <button
              v-else-if="item === 'forget'"
              type="button"
              class="btn stationpanel-forget"
              :class="{ danger: armed }"
              :aria-label="itemLabel(item, row, armed)"
              :data-item="item"
              @click="choose(item)"
            >
              <TwoWords :second="armed">
                <template #first>{{ itemLabel(item, row, false) }}</template>
                <template #second>{{ itemLabel(item, row, true) }}</template>
              </TwoWords>
            </button>
            <button v-else type="button" class="btn" :data-item="item" @click="choose(item)">
              {{ itemLabel(item, row, false) }}
            </button>
          </template>
        </div>
        <fieldset v-if="row.kind === 'station'" class="stationpanel-traffic">
          <legend>{{ t("station.traffic.label") }}</legend>
          <StationTraffic :call="row.call" />
        </fieldset>
        <div v-if="canMessage(row) || canAlert(row)" class="stationpanel-settings">
          <fieldset v-if="canMessage(row) && shown">
            <legend>{{ t("route.button") }}</legend>
            <StationPrefs
              :call="row.call"
              :paths="paths"
              :fallback-path="fallback"
              :rf-only="prefs.rfOnly.value"
              :heard="heardPaths.get(row.call) ?? null"
              :radios="choices"
              :choice="choice"
              :auto="auto"
              :fixed="fixed"
              :path-shown="pathShown"
              :pathless="pathless"
              :reply="reply"
              @path="setPath"
              @clear-path="clearPath"
              @set-rf-only="prefs.setRfOnly"
              @radio="chooseRadio"
            />
          </fieldset>
          <StationAlertChoices
            v-if="canAlert(row)"
            v-model:on-air="onAir"
            v-model:near="near"
            v-model:km="km"
            v-model:direct="direct"
            :call="row.call"
            :placed="home !== null"
            :km-ok="kmOk"
            @change="saveAlert"
          />
        </div>
      </div>
    </fieldset>
  </section>
</template>
