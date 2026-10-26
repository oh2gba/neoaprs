<script setup lang="ts">
// The page: a calm header (the title, a link to the project's page, and the messages not seen), the map filling the page, and at its right a panel with the stations, what is nearby, the packets, the messages, the email, the bulletins, our objects, the beacon and the settings (which open with the state of the radio link), and under the open tab a footer with the version, a newer version if there is one and what is wrong with the radio link, if anything.
// A daemon of another protocol or another build of the page makes it a notice (`VersionMismatch`) instead of the page.
// The layout only: the page put together, and what the panes share (the daemon's state, `send`, the settings, the guide, the panel), is `useAppShell`; a pane takes from the context what is the page's as a whole, and as props what is its own (the rows it lists, the one that is open).
import AppHeader from "@/components/AppHeader.vue";
import BeaconPane from "@/components/BeaconPane.vue";
import BulletinsPane from "@/components/BulletinsPane.vue";
import EmailPane from "@/components/EmailPane.vue";
import MapPickBar from "@/components/MapPickBar.vue";
import MessagesPane from "@/components/MessagesPane.vue";
import NearbyPane from "@/components/NearbyPane.vue";
import ObjectsPane from "@/components/ObjectsPane.vue";
import PacketsLog from "@/components/PacketsLog.vue";
import PanelFooter from "@/components/PanelFooter.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import SetupGuide from "@/components/SetupGuide.vue";
import SidePanel from "@/components/SidePanel.vue";
import StationCards from "@/components/StationCards.vue";
import StationMap from "@/components/StationMap.vue";
import StationsTable from "@/components/StationsTable.vue";
import FindRadioToast from "@/components/FindRadioToast.vue";
import ToastBar from "@/components/ToastBar.vue";
import { refusedAtField } from "@/lib/settinglinks";
import UpdateDialog from "@/components/UpdateDialog.vue";
import VersionMismatch from "@/components/VersionMismatch.vue";
import { useAppShell } from "@/composables/useAppShell";

const {
  daemon,
  call,
  pills,
  unread,
  openUnread,
  updateOpen,
  newer,
  talk,
  mail,
  board,
  objects,
  picks,
  layout,
  cards,
  guide,
  panel,
  notice,
  findRadio,
  stationActions,
} = useAppShell();
const { send, ownObjects, ownBulletins, bulletins, packets, lastError, mismatch } = daemon;
const { stationPick, pickingTab } = picks;
const { selected, focus } = cards;
const retry = (id: number): boolean => send({ cmd: "message_retry", id });
const cancel = (id: number): boolean => send({ cmd: "message_cancel", id });
const deleteMessage = (id: number): boolean => send({ cmd: "message_delete", id });
</script>

<template>
  <VersionMismatch v-if="mismatch" :mismatch="mismatch" />
  <div v-else class="app" :class="layout.rootClass.value">
    <AppHeader
      :call="call"
      :unread="unread"
      :pills="pills"
      :update="layout.phone.value ? newer : null"
      @messages="openUnread"
      @setup="guide.show()"
      @update="updateOpen = true"
      @open="(target) => panel.show(target)"
    />
    <UpdateDialog v-if="updateOpen && newer" :version="newer" @close="updateOpen = false" />
    <main class="main">
      <div class="mapwrap">
        <StationMap
          :selected="cards.mapSelected.value"
          :others="cards.mapOthers.value"
          :focus="focus"
          :picking="guide.picking || objects.picking || stationPick.picking.value"
          :pin="guide.open ? guide.pin : objects.pin"
          @select="cards.onMarker"
          @pick="picks.onPick"
          @move="objects.move"
          @download="panel.show('settings')"
        />
        <SetupGuide />
        <MapPickBar v-if="layout.phone.value && pickingTab" @cancel="picks.cancel" />
        <StationCards
          v-model:places="cards.places.value"
          :rows="cards.rows.value"
          :pinned="cards.pinned.value"
          :size="layout.size.value"
          @close="cards.close"
          @close-all="cards.closeAll"
          @pin="cards.pin"
          @message-all="talk.openGroup"
          @overflow="cards.closeOldest"
          @weather="(call, hours) => send({ cmd: 'weather_series', call, hours })"
          @forget="cards.forget"
          @edit="objects.edit"
          @kill="objects.kill"
          @message="talk.writeTo"
        />
      </div>
      <SidePanel
        v-model:tab="panel.tab.value"
        v-model:collapsed="panel.collapsed.value"
        v-model:width="panel.width.value"
        :size="layout.size.value"
        :view="layout.showing.value"
        :badges="{ messages: talk.unread.value, email: mail.unread.value, bulletins: board.fresh.value }"
        @update:view="layout.view.value = $event"
      >
        <template #footer>
          <PanelFooter @update="updateOpen = true" @radio="panel.show('settings')" />
        </template>
        <template #stations>
          <StationsTable
            :selected="selected"
            :others="cards.others.value"
            @select="cards.onRow"
            @message="talk.writeTo"
            @forget="cards.forget"
            @ask="stationActions.ask"
            @copy="stationActions.copy"
          />
        </template>
        <template #nearby>
          <NearbyPane :selected="selected" :others="cards.others.value" @select="cards.onRow" />
        </template>
        <template #packets>
          <PacketsLog :packets="packets" />
        </template>
        <template #messages>
          <MessagesPane
            :conversations="talk.list.value"
            :selected="talk.selected.value"
            :thread="talk.thread.value"
            :show-overheard="talk.showOverheard.value"
            :group="talk.group.value"
            @update:show-overheard="talk.showOverheard.value = $event"
            @update:group="talk.group.value = $event"
            @select="talk.selected.value = $event"
            @delete-conversation="talk.deleteConversation"
            @delete-overheard="talk.deleteOverheard"
            @send="talk.sendMessage"
            @send-many="talk.sendMessages"
            @retry="retry"
            @cancel="cancel"
            @delete-message="deleteMessage"
          />
        </template>
        <template #email>
          <EmailPane
            :thread="mail.thread.value"
            :addresses="mail.addresses.value"
            :fresh-after="mail.freshAfter.value"
            @send="mail.sendMail"
            @forget="mail.forget"
            @get="mail.checkMail"
            @delete="mail.remove"
            @retry="retry"
            @cancel="cancel"
          />
        </template>
        <template #bulletins>
          <BulletinsPane :bulletins="bulletins" :own-bulletins="ownBulletins" />
        </template>
        <template #objects>
          <ObjectsPane :objects="ownObjects" :form="objects" @select="cards.pickFromTable" />
        </template>
        <template #beacon>
          <BeaconPane :picking="stationPick.picking.value" :picked="stationPick.picked.value" @pick-position="stationPick.toggle()" />
        </template>
        <template #settings>
          <SettingsForm @setup="guide.show()" @update="updateOpen = true" />
        </template>
      </SidePanel>
    </main>
    <ToastBar :toast="refusedAtField(lastError) ? null : lastError" :notice="notice" />
    <FindRadioToast :find="findRadio" />
  </div>
</template>
