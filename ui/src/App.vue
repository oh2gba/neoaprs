<script setup lang="ts">
// The page: a header with the connection and the radio link, the map filling the page, and at its right a panel with the stations, the packets, the messages, the email, the bulletins, our objects, the beacon and the settings (which open with the state of the radio link).
// The shell only: what the daemon tells is `useDaemon`, the panel `usePanel`, the station cards (one, or several with Ctrl+click) `useStationCards`, the size of the page and what a phone shows `useLayout`, the Messages tab `useMessagesView`, the Email tab `useEmail`, the Bulletins tab `useBulletins`, the Objects tab `useOwnObjects`, the paths, timeouts and RF only of the stations
// `useStationPrefs`, the settings of the Beacon tab and the Settings tab, which apply as they are changed (one queue for both, and the toast that undoes the latest change) `useSettings`, the first-run guide (it opens by itself while the daemon has no call) `useSetupGuide`, the alert of this browser for a message to us `useBrowserAlerts` and `usePageAlerts`; the components take props and emit events, and the commands go out through `send`.
import { useMapPicks } from "@/composables/useMapPicks";
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
import MapPickBar from "@/components/MapPickBar.vue";
import StationCards from "@/components/StationCards.vue";
import StationMap from "@/components/StationMap.vue";
import StationsTable from "@/components/StationsTable.vue";
import RadioStatus from "@/components/RadioStatus.vue";
import ToastBar from "@/components/ToastBar.vue";
import UndoToast from "@/components/UndoToast.vue";
import UpdatePanel from "@/components/UpdatePanel.vue";
import { useBrowserAlerts } from "@/composables/useBrowserAlerts";
import { useLayout } from "@/composables/useLayout";
import { useBulletins } from "@/composables/useBulletins";
import { useDaemon } from "@/composables/useDaemon";
import { useDark } from "@/composables/useDark";
import { useEmail } from "@/composables/useEmail";
import { useMessagesView } from "@/composables/useMessagesView";
import { useNow } from "@/composables/useNow";
import { usePageAlerts } from "@/composables/usePageAlerts";
import { useOwnObjects } from "@/composables/useOwnObjects";
import { usePanel } from "@/composables/usePanel";
import { useStationCards } from "@/composables/useStationCards";
import { useSettings } from "@/composables/useSettings";
import { useSetupGuide } from "@/composables/useSetupGuide";
import { useStationPrefs } from "@/composables/useStationPrefs";
import { useTitle } from "@/composables/useTitle";
import { DEFAULT_TIMEOUT_MIN, type Aging } from "@/lib/aging";
import { filesKey } from "@/lib/mapfetch";
import { candidates as messageCandidates } from "@/lib/recipients";
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
const settings = useSettings(config, lastError, send);
const stations = computed(() => withOwnSymbol(heard, config.value?.values));
const { paths: stationPaths, timeouts, rfOnly, setRfOnly, setPath, clearPath, setTimeoutMin, clearTimeoutMin } = useStationPrefs(stationPrefs, send);
const aging = computed<Aging>(() => ({ timeouts: timeouts.value, defaultMin: DEFAULT_TIMEOUT_MIN }));
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
const talk = useMessagesView(messages, panel, send);
const mail = useEmail(messages, panel, send);
const board = useBulletins(bulletins, panel);
const alerts = useBrowserAlerts(talk.writeTo);
usePageAlerts(messages, messagesLoaded, alerts.announce);
// the messages not seen, those of the Messages tab and those of the email gateway: one count, the one of the header, of the folded panel's handle and of the browser tab's title
const unread = computed(() => talk.unread.value + mail.unread.value);
useTitle(unread, alerts.tabTitle);
/** The mail of the header: the Messages tab, or the Email tab when the messages not seen are all the gateway's. */
function openUnread(): void {
  if (talk.unread.value > 0 || mail.unread.value === 0) talk.openMessages();
  else panel.show("email");
}
const suggestions = computed(() => new Map([...stations.value].map(([call, row]) => [call, row.suggested_path] as const)));
const heardDirect = computed(() => new Set([...stations.value].filter(([, row]) => row.heard_direct > 0).map(([call]) => call)));
const fallbackPath = computed(() => config.value?.values["beacon/path"] ?? "");
const connected = computed(() => tnc.value?.state === "connected");

const call = computed<string | null>(() => config.value?.values["station/call"] ?? status.value?.call ?? null);
const candidates = computed(() => messageCandidates(stations.value, call.value, now.value));
const home = computed<Home | null>(() => {
  const place = (text: string | number | null | undefined): number => (text === undefined || text === null || text === "" ? NaN : Number(text));
  const lat = place(config.value?.values["station/lat"] ?? status.value?.lat);
  const lon = place(config.value?.values["station/lon"] ?? status.value?.lon);
  return Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null;
});
const objects = useOwnObjects(ownObjects, home, send, panel);

const picks = useMapPicks(guide, objects);
const { stationPick, pickingTab } = picks;

// the size of the page, what a phone shows (the map or the tab), and the station cards: one, or several with Ctrl+click on a desktop and a tablet
const layout = useLayout(
  panel,
  computed(() => guide.open),
  pickingTab,
);
const cards = useStationCards(stations, send, layout, () => guide.open || updateOpen.value);
const { selected, focus } = cards;
</script>

<template>
  <div class="app" :class="layout.rootClass.value">
    <AppHeader
      :call="call"
      :connection="connection"
      :tnc="tnc"
      :version="version"
      :unread="unread"
      :now="now"
      :status="status"
      @messages="openUnread"
      @setup="guide.show()"
      @update="updateOpen = true"
      @radio="panel.show('settings')"
    />
    <UpdatePanel v-if="updateOpen && newer" :version="newer" :install="install" @close="updateOpen = false" />
    <main class="main">
      <div class="mapwrap">
        <StationMap
          :stations="stations"
          :selected="selected"
          :others="cards.others.value"
          :focus="focus"
          :home="home"
          :now="now"
          :dark="dark"
          :aging="aging"
          :files-key="filesKey(map)"
          :picking="guide.picking || objects.picking || stationPick.picking.value"
          :pin="guide.open ? guide.pin : objects.pin"
          @select="cards.onMarker"
          @pick="picks.onPick"
          @move="objects.move"
          @download="panel.show('settings')"
        />
        <SetupGuide :guide="guide" :config="config" :map="map" />
        <MapPickBar v-if="layout.phone.value && pickingTab" @cancel="picks.cancel" />
        <StationCards
          :rows="cards.rows.value"
          :size="layout.size.value"
          :now="now"
          :aging="aging"
          :weather-series="weatherSeries"
          @close="cards.close"
          @close-all="cards.closeAll"
          @only="selected = $event"
          @weather="(call, hours) => send({ cmd: 'weather_series', call, hours })"
          @forget="cards.forget"
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
        :size="layout.size.value"
        :view="layout.showing.value"
        :badges="{ messages: talk.unread.value, email: mail.unread.value, bulletins: board.fresh.value }"
        @update:view="layout.view.value = $event"
      >
        <template #stations>
          <StationsTable :stations="stations" :selected="selected" :others="cards.others.value" :now="now" :aging="aging" @select="cards.onRow" />
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
            :paths="stationPaths"
            :suggestions="suggestions"
            :fallback-path="fallbackPath"
            :rf-only="rfOnly"
            :heard-direct="heardDirect"
            :candidates="candidates"
            @update:show-overheard="talk.showOverheard.value = $event"
            @path="setPath"
            @clear-path="clearPath"
            @set-rf-only="setRfOnly"
            @select="talk.selected.value = $event"
            @delete-conversation="talk.deleteConversation"
            @delete-overheard="talk.deleteOverheard"
            @send="talk.sendMessage"
            @send-many="talk.sendMessages"
            @retry="send({ cmd: 'message_retry', id: $event })"
            @cancel="send({ cmd: 'message_cancel', id: $event })"
          />
        </template>
        <template #email>
          <EmailPane
            :thread="mail.thread.value"
            :connected="connected"
            :addresses="mail.addresses.value"
            :fresh-after="mail.freshAfter.value"
            :heard-direct="heardDirect"
            @send="mail.sendMail"
            @forget="mail.forget"
            @register="mail.registerShortcut"
            @list="mail.listShortcuts"
            @remove="mail.removeShortcut"
            @get="mail.getHeld"
            @delete="mail.remove"
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
            :settings="settings"
            :picking="stationPick.picking.value"
            :picked="stationPick.picked.value"
            @beacon="send({ cmd: 'beacon_now' })"
            @status="send({ cmd: 'status_now' })"
            @pick-position="stationPick.toggle()"
          />
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
            :settings="settings"
            @setup="guide.show()"
            @update="updateOpen = true"
          >
            <template #radio
              ><RadioStatus :tnc="tnc" :now="now" :digipeater="config?.values['digi/enabled'] === 'true'" @reconnect="send({ cmd: 'tnc_reconnect' })"
            /></template>
            <template #notifications><BrowserAlerts :alerts="alerts" :https="config?.https" /></template>
          </SettingsForm>
        </template>
      </SidePanel>
    </main>
    <UndoToast :undo="settings.undo.value" @undo="settings.undoLast()" @dismiss="settings.dismissUndo()" />
    <ToastBar :toast="lastError" />
  </div>
</template>
