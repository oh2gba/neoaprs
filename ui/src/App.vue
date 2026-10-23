<script setup lang="ts">
// The page: a header with the connection and the radio link, the map filling the page, and at its right a panel with the stations, the packets, the messages, the email, the bulletins, our objects, the beacon, the TNC and the settings.
// The shell only: what the daemon tells is `useDaemon`, the panel `usePanel`, the station picked `useSelection`, the Messages tab `useMessagesView`, the Email tab `useEmail`, the Bulletins tab `useBulletins`, the Objects tab `useOwnObjects`, the paths, timeouts and attempts of the stations
// `useStationPrefs`, the first-run guide (it opens by itself while the daemon has no call) `useSetupGuide`, the alert of this browser for a message to us `useBrowserAlerts` and `usePageAlerts`; the components take props and emit events, and the commands go out through `send`.
import { usePositionPick } from "@/composables/usePositionPick";
import { computed, ref, watch } from "vue";
import AppHeader from "@/components/AppHeader.vue";
import BeaconPane from "@/components/BeaconPane.vue";
import BrowserAlerts from "@/components/BrowserAlerts.vue";
import BulletinsPane from "@/components/BulletinsPane.vue";
import EmailPane from "@/components/EmailPane.vue";
import MessagesPane from "@/components/MessagesPane.vue";
import ObjectsPane from "@/components/ObjectsPane.vue";
import PacketsLog from "@/components/PacketsLog.vue";
import SetupGuide from "@/components/SetupGuide.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import SidePanel from "@/components/SidePanel.vue";
import StationCard from "@/components/StationCard.vue";
import StationMap from "@/components/StationMap.vue";
import StationsTable from "@/components/StationsTable.vue";
import TncPanel from "@/components/TncPanel.vue";
import ToastBar from "@/components/ToastBar.vue";
import UpdatePanel from "@/components/UpdatePanel.vue";
import { useBrowserAlerts } from "@/composables/useBrowserAlerts";
import { useBulletins } from "@/composables/useBulletins";
import { useDaemon } from "@/composables/useDaemon";
import { useDark } from "@/composables/useDark";
import { useEmail } from "@/composables/useEmail";
import { useMessagesView } from "@/composables/useMessagesView";
import { useNow } from "@/composables/useNow";
import { usePageAlerts } from "@/composables/usePageAlerts";
import { useOwnObjects } from "@/composables/useOwnObjects";
import { usePanel } from "@/composables/usePanel";
import { useSelection } from "@/composables/useSelection";
import { useSetupGuide } from "@/composables/useSetupGuide";
import { useStationPrefs } from "@/composables/useStationPrefs";
import { useTitle } from "@/composables/useTitle";
import { defaultTimeoutMin, type Aging } from "@/lib/aging";
import { defaultAttempts, type Attempts } from "@/lib/attempts";
import { filesKey } from "@/lib/mapfetch";
import { withOwnSymbol } from "@/lib/stations";
import type { Home } from "@/lib/mapview";

const {
  stations: heard,
  packets,
  messages,
  messagesLoaded,
  bulletins,
  ownObjects,
  ownBulletins,
  stationPrefs,
  tnc,
  config,
  map,
  status,
  connection,
  lastError,
  version,
  install,
  weatherSeries,
  alertResult,
  updateResult,
  ports,
  send,
} = useDaemon();
// the ports the system lists, for the Settings tab and the setup guide: asked each time the daemon is connected (not before: a command then is refused with a toast)
watch(connection, (state) => {
  if (state === "open") send({ cmd: "list_ports" });
});
const stations = computed(() => withOwnSymbol(heard, config.value?.values));
const {
  paths: stationPaths,
  timeouts,
  attempts: ownAttempts,
  rfOnly,
  setRfOnly,
  setPath,
  clearPath,
  setTimeoutMin,
  clearTimeoutMin,
  setAttempts,
  clearAttempts,
} = useStationPrefs(stationPrefs, send);
const aging = computed<Aging>(() => ({ timeouts: timeouts.value, defaultMin: defaultTimeoutMin(config.value?.values) }));
const attempts = computed<Attempts>(() => ({ own: ownAttempts.value, defaultCount: defaultAttempts(config.value?.values) }));
// the panel with the steps of an update is open on purpose, and goes when the newer version does
const updateOpen = ref(false);
const newer = computed(() => status.value?.update?.version ?? null);
watch(newer, (version) => version === null && (updateOpen.value = false));
const now = useNow();
const dark = useDark();
const guide = useSetupGuide(config, lastError, ports, send);
let guideShown = false;
// the guide opens once, when the daemon says it has no call (the page's first word of a fresh install)
watch(
  () => config.value?.values["station/call"] === "",
  (empty) => {
    if (empty && !guideShown) {
      guideShown = true;
      guide.show();
    }
  },
  { immediate: true },
);

const panel = usePanel();
const { tab, collapsed, width } = panel;
const { selected, focus, row: selectedRow, pickFromTable, forget } = useSelection(stations, send);
const talk = useMessagesView(messages, panel, send);
const mail = useEmail(messages, panel, send, ownAttempts);
const board = useBulletins(bulletins, panel);
const alerts = useBrowserAlerts(talk.writeTo);
usePageAlerts(messages, messagesLoaded, alerts.announce);
useTitle(
  computed(() => talk.unread.value + mail.unread.value),
  alerts.tabTitle,
);
const suggestions = computed(() => new Map([...stations.value].map(([call, row]) => [call, row.suggested_path] as const)));
const heardDirect = computed(() => new Set([...stations.value].filter(([, row]) => row.heard_direct > 0).map(([call]) => call)));
const fallbackPath = computed(() => config.value?.values["beacon/path"] ?? "");
const connected = computed(() => tnc.value?.state === "connected");

const call = computed<string | null>(() => config.value?.values["station/call"] ?? status.value?.call ?? null);
const home = computed<Home | null>(() => {
  const place = (text: string | number | null | undefined): number => (text === undefined || text === null || text === "" ? NaN : Number(text));
  const lat = place(config.value?.values["station/lat"] ?? status.value?.lat);
  const lon = place(config.value?.values["station/lon"] ?? status.value?.lon);
  return Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null;
});
const objects = useOwnObjects(ownObjects, home, send, panel);

/** A click on the map is a place for the first-run guide while it asks for one, else for the form of an object. */
const stationPick = usePositionPick(); // the Beacon tab's Pick on the map
function onPick(at: Home): void {
  if (guide.picking) guide.place(at.lat, at.lon);
  else if (stationPick.picking.value) stationPick.place(at.lat, at.lon);
  else objects.place(at.lat, at.lon);
}
</script>

<template>
  <div class="app">
    <AppHeader
      :call="call"
      :connection="connection"
      :tnc="tnc"
      :version="version"
      :unread="talk.unread.value"
      :now="now"
      :status="status"
      @messages="talk.openMessages"
      @setup="guide.show()"
      @update="updateOpen = true"
    />
    <UpdatePanel v-if="updateOpen && newer" :version="newer" :install="install" @close="updateOpen = false" />
    <main class="main">
      <div class="mapwrap">
        <StationMap
          :stations="stations"
          :selected="selected"
          :focus="focus"
          :home="home"
          :now="now"
          :dark="dark"
          :aging="aging"
          :files-key="filesKey(map)"
          :picking="guide.picking || objects.picking || stationPick.picking.value"
          :pin="guide.open ? guide.pin : objects.pin"
          @select="selected = $event"
          @pick="onPick"
          @move="objects.move"
          @download="panel.show('settings')"
        />
        <SetupGuide :guide="guide" :config="config" :map="map" />
        <StationCard
          v-if="selectedRow"
          :row="selectedRow"
          :now="now"
          :aging="aging"
          :weather-series="weatherSeries"
          @close="selected = null"
          @weather="(call, hours) => send({ cmd: 'weather_series', call, hours })"
          @forget="forget"
          @edit="objects.edit"
          @kill="objects.kill"
          @message="talk.writeTo"
          @timeout="setTimeoutMin"
          @clear-timeout="clearTimeoutMin"
        />
      </div>
      <SidePanel
        v-model:tab="tab"
        v-model:collapsed="collapsed"
        v-model:width="width"
        :badges="{ messages: talk.unread.value, email: mail.unread.value, bulletins: board.fresh.value }"
      >
        <template #stations>
          <StationsTable :stations="stations" :selected="selected" :now="now" :aging="aging" @select="pickFromTable" />
        </template>
        <template #packets>
          <PacketsLog :packets="packets" />
        </template>
        <template #messages>
          <MessagesPane
            :conversations="talk.list.value"
            :selected="talk.selected.value"
            :thread="talk.thread.value"
            :connected="connected"
            :now="now"
            :show-overheard="talk.showOverheard.value"
            :attempts="attempts"
            :paths="stationPaths"
            :suggestions="suggestions"
            :fallback-path="fallbackPath"
            :rf-only="rfOnly"
            :heard-direct="heardDirect"
            @update:show-overheard="talk.showOverheard.value = $event"
            @path="setPath"
            @clear-path="clearPath"
            @set-attempts="setAttempts"
            @clear-attempts="clearAttempts"
            @set-rf-only="setRfOnly"
            @select="talk.selected.value = $event"
            @delete-conversation="talk.deleteConversation"
            @delete-overheard="talk.deleteOverheard"
            @send="talk.sendMessage"
            @retry="send({ cmd: 'message_retry', id: $event })"
            @cancel="send({ cmd: 'message_cancel', id: $event })"
          />
        </template>
        <template #email>
          <EmailPane
            :thread="mail.thread.value"
            :connected="connected"
            :addresses="mail.addresses.value"
            :attempts="attempts"
            :heard-direct="heardDirect"
            @send="mail.sendMail"
            @forget="mail.forget"
            @register="mail.registerShortcut"
            @list="mail.listShortcuts"
            @remove="mail.removeShortcut"
            @get="mail.getHeld"
            @set-attempts="setAttempts"
            @clear-attempts="clearAttempts"
            @retry="send({ cmd: 'message_retry', id: $event })"
            @cancel="send({ cmd: 'message_cancel', id: $event })"
          />
        </template>
        <template #bulletins>
          <BulletinsPane
            :bulletins="bulletins"
            :own-bulletins="ownBulletins"
            :call="call"
            :now="now"
            @delete="(sender, slot) => send({ cmd: 'bulletin_delete', sender, slot })"
            @post="(slot, text) => send({ cmd: 'bulletin_post', slot, text })"
            @unpost="(slot) => send({ cmd: 'bulletin_unpost', slot })"
          />
        </template>
        <template #objects>
          <ObjectsPane :objects="ownObjects" :form="objects" :fallback-path="fallbackPath" :now="now" />
        </template>
        <template #beacon>
          <BeaconPane
            :status="status"
            :connected="connected"
            :now="now"
            :config="config"
            :last-error="lastError"
            :send="send"
            :picking="stationPick.picking.value"
            :picked="stationPick.picked.value"
            @beacon="send({ cmd: 'beacon_now' })"
            @pick-position="stationPick.toggle()"
          />
        </template>
        <template #tnc>
          <TncPanel :tnc="tnc" :now="now" @reconnect="send({ cmd: 'tnc_reconnect' })" />
        </template>
        <template #settings>
          <SettingsForm
            :config="config"
            :last-error="lastError"
            :alert-result="alertResult"
            :update-result="updateResult"
            :map="map"
            :ports="ports"
            :send="send"
            @setup="guide.show()"
            @update="updateOpen = true"
          >
            <template #notifications><BrowserAlerts :alerts="alerts" /></template>
          </SettingsForm>
        </template>
      </SidePanel>
    </main>
    <ToastBar :toast="lastError" />
  </div>
</template>
