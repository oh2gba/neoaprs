<script setup lang="ts">
// The station panel of the Stations tab: what a click on a row shows, fixed at the bottom of the tab as the box of every tab is (the group box of the Bulletins and Email tabs: styles/compose.css), with the station's call
// as its legend and a cross at its right that closes it (Esc anywhere in it too: `close`, and the parent gives the focus back to the row). It has a height of its own (half the tab, two fifths on a phone), the same whichever station it shows and whatever comes,
// and what does not fit in it scrolls inside it, so that the list above never moves. In it, in this order: Message and the directed queries (Ask for weather only to a weather station, lib/stations.ts `panelItems`) with
// the operator's own query under them (StationQuery), for a station that takes messages; Show on map (or its card), Copy call, the QRZ page and, at the end of the line, Forget, which asks twice like the row's trash can
// ("Really forget?", the same 5 s; its button keeps the width of the longer words, so that nothing moves); the station's traffic, as the lines of the Packets tab, with the state of each query of ours (StationTraffic); and
// the route of messages to it (StationPrefs: its path and RF only, as under "Route" of a conversation) and "Alert me when…" (StationAlertChoices; a station heard that is not ours), in group boxes side by side when there is
// room, saved as each is changed. Our own station has Show, Copy and QRZ, an object of ours Show and Copy, another's object Show, Copy and Forget. The buttons say what they do with events, and the parent does it.
import { computed } from "vue";
import IconButton from "@/components/IconButton.vue";
import MessageGlyph from "@/components/MessageGlyph.vue";
import StationAlertChoices from "@/components/StationAlertChoices.vue";
import StationPrefs from "@/components/StationPrefs.vue";
import StationQuery from "@/components/StationQuery.vue";
import StationTraffic from "@/components/StationTraffic.vue";
import { useAlertDraft } from "@/composables/useAlertDraft";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useReceiveOnly } from "@/composables/useReceiveOnly";
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
const { prefs, heardPaths, fallbackPath, home } = useDaemonContext();
const rxOnly = useReceiveOnly();

const items = computed(() => panelItems(props.row));
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
  <section class="composebar boxed stationpanel" :aria-label="t('station.row.label', { call: row.call })" @keydown.esc="onEsc">
    <fieldset class="composebox stationpanel-box">
      <legend class="stationpanel-legend">
        <span class="mono">{{ row.call }}</span>
        <IconButton kind="close" :label="t('station.panel.close')" :title="t('station.panel.close')" @click="emit('close')" />
      </legend>
      <div class="stationpanel-body">
        <div v-if="talk.length > 0" class="stationpanel-line">
          <button
            v-for="item in talk"
            :key="item"
            type="button"
            class="btn"
            :class="{ primary: item === 'message', msgbtn: item === 'message' }"
            :disabled="rxOnly && item !== 'message'"
            :title="rxOnly && item !== 'message' ? rxOnlyReason() : item === 'ask_weather' ? t('station.menu.ask_weather_title') : undefined"
            :data-item="item"
            @click="choose(item)"
          >
            <MessageGlyph v-if="item === 'message'" :size="14" />{{ itemLabel(item, row, false) }}
          </button>
        </div>
        <StationQuery v-if="canMessage(row)" :call="row.call" @ask="(text) => emit('ask', row.call, 'custom', text)" />
        <div class="stationpanel-line">
          <template v-for="item in rest" :key="item">
            <a v-if="item === 'qrz'" class="btn" :href="qrz" target="_blank" rel="noopener noreferrer" :data-item="item">{{ itemLabel(item, row, false) }}</a>
            <button
              v-else-if="item === 'forget'"
              type="button"
              class="btn stationpanel-forget"
              :class="{ danger: armed }"
              :aria-label="itemLabel(item, row, armed)"
              :data-item="item"
              @click="choose(item)"
            >
              <span class="twowords"
                ><span :class="{ 'twowords-off': armed }">{{ itemLabel(item, row, false) }}</span
                ><span :class="{ 'twowords-off': !armed }">{{ itemLabel(item, row, true) }}</span></span
              >
            </button>
            <button v-else type="button" class="btn" :data-item="item" @click="choose(item)">{{ itemLabel(item, row, false) }}</button>
          </template>
        </div>
        <fieldset v-if="row.kind === 'station'" class="stationpanel-traffic">
          <legend>{{ t("station.traffic.label") }}</legend>
          <StationTraffic :call="row.call" />
        </fieldset>
        <div v-if="canMessage(row) || canAlert(row)" class="stationpanel-settings">
          <fieldset v-if="canMessage(row)">
            <legend>{{ t("route.button") }}</legend>
            <StationPrefs
              :call="row.call"
              :paths="prefs.paths.value"
              :fallback-path="fallbackPath"
              :rf-only="prefs.rfOnly.value"
              :heard="heardPaths.get(row.call) ?? null"
              @path="prefs.setPath"
              @clear-path="prefs.clearPath"
              @set-rf-only="prefs.setRfOnly"
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
