<script setup lang="ts">
// What a click on a row of the Stations table opens under it (as a click on a packet does in the Packets tab): what the menu of the row offers, as buttons in plain view, and the station's settings. First Message and the four
// directed queries with the short line that many stations do not answer them (a station that takes messages), then Show on map (or its card), Copy call, the QRZ page and, at the end of the line, Forget, which asks twice like
// the row's trash can ("Really forget?", the same 5 s; its button keeps the width of the longer words, so that nothing moves). Under them, in group boxes side by side when there is room: the route of messages to the station
// (StationPrefs: its path and RF only, as under "Route" of a conversation; a station that takes messages) and "Alert me when…" (StationAlertChoices; a station heard that is not ours), saved as each is changed. Our own station
// has Show, Copy and QRZ, an object of ours Show and Copy, another's object Show, Copy and Forget (lib/stations.ts, `menuItems`). The buttons say what they do with the events of the menu (StationMenu), and the parent does it;
// Esc anywhere in the field is `close` (the parent gives the focus back to the row). The field never makes the table wider: it takes the width the columns have.
import { computed } from "vue";
import MessageGlyph from "@/components/MessageGlyph.vue";
import StationAlertChoices from "@/components/StationAlertChoices.vue";
import StationPrefs from "@/components/StationPrefs.vue";
import { useAlertDraft } from "@/composables/useAlertDraft";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useReceiveOnly } from "@/composables/useReceiveOnly";
import { t } from "@/i18n";
import { qrzUrl } from "@/lib/calls";
import { rxOnlyReason } from "@/lib/compose";
import { canAlert } from "@/lib/stationalert";
import { canMessage, menuGroup, menuItems, menuLabel, menuQuery, type MenuItem, type QueryKind } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";

const props = defineProps<{ row: StationRow; armed: boolean }>();
const emit = defineEmits<{
  close: [];
  message: [call: string];
  ask: [call: string, kind: QueryKind];
  show: [call: string];
  copy: [call: string];
  forget: [call: string];
}>();
const { prefs, heardPaths, fallbackPath, home } = useDaemonContext();
const rxOnly = useReceiveOnly();

/** The menu's items but its "Alert me when…", whose choices are in the field itself: talking to the station, and the rest. */
const items = computed(() => menuItems(props.row).filter((item) => item !== "alert"));
const talk = computed(() => items.value.filter((item) => menuGroup(item) === 0));
const rest = computed(() => items.value.filter((item) => menuGroup(item) !== 0));
const qrz = computed(() => qrzUrl(props.row.call) ?? undefined);

const { onAir, near, km, direct, kmOk, alert } = useAlertDraft(() => prefs.alerts.value.get(props.row.call) ?? null, true);
function saveAlert(): void {
  const value = alert();
  if (value !== null) prefs.setAlert(props.row.call, value);
}

function choose(item: MenuItem): void {
  const call = props.row.call;
  const kind = menuQuery(item);
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
  <div class="stationfield" role="group" :aria-label="t('station.row.label', { call: row.call })" @keydown.esc="onEsc">
    <div v-if="talk.length > 0" class="stationfield-line">
      <button
        v-for="item in talk"
        :key="item"
        type="button"
        class="btn"
        :class="{ primary: item === 'message', msgbtn: item === 'message' }"
        :disabled="rxOnly && item !== 'message'"
        :title="rxOnly && item !== 'message' ? rxOnlyReason() : undefined"
        :data-item="item"
        @click="choose(item)"
      >
        <MessageGlyph v-if="item === 'message'" :size="14" />{{ menuLabel(item, row, false) }}
      </button>
    </div>
    <p v-if="talk.length > 1" class="stationfield-note muted">{{ t("station.menu.note") }}</p>
    <div class="stationfield-line">
      <template v-for="item in rest" :key="item">
        <a v-if="item === 'qrz'" class="btn" :href="qrz" target="_blank" rel="noopener noreferrer" :data-item="item">{{ menuLabel(item, row, false) }}</a>
        <button
          v-else-if="item === 'forget'"
          type="button"
          class="btn stationfield-forget"
          :class="{ danger: armed }"
          :aria-label="menuLabel(item, row, armed)"
          :data-item="item"
          @click="choose(item)"
        >
          <span class="twowords"
            ><span :class="{ 'twowords-off': armed }">{{ menuLabel(item, row, false) }}</span
            ><span :class="{ 'twowords-off': !armed }">{{ menuLabel(item, row, true) }}</span></span
          >
        </button>
        <button v-else type="button" class="btn" :data-item="item" @click="choose(item)">{{ menuLabel(item, row, false) }}</button>
      </template>
    </div>
    <div v-if="canMessage(row) || canAlert(row)" class="stationfield-settings">
      <fieldset v-if="canMessage(row)" class="stationfield-route">
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
</template>
