<script setup lang="ts">
// The Beacon tab: the settings the beacon and the status are made from (our station and where its position comes from, the beacon, the status), which apply as they are changed like the Settings tab's. The buttons that send now are where their words are: the beacon status at the top of the tab
// (BeaconStatus: for a fixed station when the last beacon went and when the next is due, for a moving one the GPS and what SmartBeaconing does, with Beacon now), and, while a status is chosen (in the form, as it is being changed), the status last sent with Send status now at the top of the
// Status group (SendRow). useSendNow says when they are on and asks twice; both are off, with a tip that says the beacon is off, while the beacon is Off.
import BeaconStatus from "@/components/BeaconStatus.vue";
import SendRow from "@/components/SendRow.vue";
import TabHelp from "@/components/TabHelp.vue";
import type { Picked } from "@/composables/usePositionPick";
import SettingsForm from "@/components/SettingsForm.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useSendNow } from "@/composables/useSendNow";
import { rxOnlyReason } from "@/lib/compose";
import { NONE } from "@/lib/format";
import { statusSource } from "@/lib/status";
import { computed, toRef } from "vue";

const props = withDefaults(defineProps<{ picking?: boolean; picked?: Picked | null }>(), { picking: false, picked: null });
const emit = defineEmits<{ pickPosition: [] }>();

const { status, connected, now, config, send, settings, gps, receiveOnly } = useDaemonContext();
const sending = useSendNow(connected, settings.saving, toRef(props, "picking"), () => emit("pickPosition"));
/** Beacon now and Send status now send while the beacon is Off (that is only no automatic beacon); RX only (transmitting switched off) is what turns them off, and the title says so. */
const ready = computed(() => sending.ready.value && !receiveOnly.value);
const why = computed(() => (receiveOnly.value ? rxOnlyReason() : sending.why.value));

const current = computed(() => {
  const text = status.value?.station_status ?? "";
  const rig = status.value?.rig_state ?? "unused";
  return `${text === "" ? NONE : text}${rig === "unused" ? "" : ` · ${t(rig === "on" ? "beacon.rigctld_on" : "beacon.rigctld_off")}`}`;
});
</script>

<template>
  <div class="beaconpane">
    <TabHelp :label="t('beacon.about_label')" picture="beacon">
      <span class="info-line">{{ t("beacon.about1") }}</span>
      <span class="info-line">{{ t("beacon.about2") }}</span>
    </TabHelp>
    <SettingsForm scope="beacon" :picking="picking" :picked="picked" @pick-position="emit('pickPosition')">
      <template #top>
        <BeaconStatus
          :status="status"
          :gps="gps"
          :values="config?.values ?? {}"
          :now="now"
          :armed="sending.armed.value === 'beacon'"
          :disabled="!ready"
          :why="why"
          @press="sending.press('beacon', () => send({ cmd: 'beacon_now' }))"
        />
      </template>
      <template #status="{ draft }">
        <SendRow
          v-if="statusSource(draft) !== 'off'"
          :label="t('beacon.status')"
          :text="current"
          :button="t('beacon.send_status_now')"
          :armed="sending.armed.value === 'status'"
          :disabled="!ready"
          :why="why"
          @press="sending.press('status', () => send({ cmd: 'status_now' }))"
        />
      </template>
    </SettingsForm>
  </div>
</template>
