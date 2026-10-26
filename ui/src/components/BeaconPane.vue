<script setup lang="ts">
// The Beacon tab: the settings the beacon and the status are made from (our station and where its position comes from, the beacon, the status), which apply as they are changed like the Settings tab's. Under the Beacon choice are the state of the beacon (BeaconStatus: the radio's
// status row; for a fixed station when the last beacon went and when the next is due, for a moving one the GPS and what SmartBeaconing does) and the row Beacon now (SendRow); under the Status choice, while a status is chosen, the status report as a row (StatusReportRow), and the row Send status now at the end of the Status group.
// useSendNow says when the buttons are on and asks twice; both are off, with a tip that says why, while the transmitter is off (RX only).
import BeaconStatus from "@/components/BeaconStatus.vue";
import SendRow from "@/components/SendRow.vue";
import StatusReportRow from "@/components/StatusReportRow.vue";
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

const current = computed(() => status.value?.station_status || NONE);
</script>

<template>
  <div class="beaconpane">
    <TabHelp :label="t('beacon.about_label')" picture="beacon">
      <span class="info-line">{{ t("beacon.about1") }}</span>
      <span class="info-line">{{ t("beacon.about2") }}</span>
    </TabHelp>
    <SettingsForm scope="beacon" :picking="picking" :picked="picked" @pick-position="emit('pickPosition')">
      <template #after="{ fieldKey, draft }">
        <template v-if="fieldKey === 'beacon/interval_min'">
          <BeaconStatus :status="status" :gps="gps" :values="config?.values ?? {}" :now="now" />
          <SendRow
            id="beacon-now"
            :label="t('beacon.now_label')"
            :tip-label="t('beacon.now_tip_label')"
            :tip="t('beacon.now_tip')"
            :button="t('beacon.beacon_now')"
            :armed="sending.armed.value === 'beacon'"
            :disabled="!ready"
            :why="why"
            @press="sending.press('beacon', () => send({ cmd: 'beacon_now' }))"
          />
        </template>
        <template v-else-if="fieldKey === 'status/source' && statusSource(draft) !== 'off'">
          <StatusReportRow :text="current" :minutes="config?.values['status/interval_min'] ?? ''" :rig="status?.rig_state ?? 'unused'" />
        </template>
        <template v-else-if="(fieldKey === 'station/status' || fieldKey === 'status/template') && statusSource(draft) !== 'off'">
          <SendRow
            id="status-now"
            :label="t('beacon.now_label')"
            :tip-label="t('beacon.status_now_tip_label')"
            :tip="t('beacon.status_now_tip')"
            :button="t('beacon.send_status_now')"
            :armed="sending.armed.value === 'status'"
            :disabled="!ready"
            :why="why"
            @press="sending.press('status', () => send({ cmd: 'status_now' }))"
          />
        </template>
      </template>
    </SettingsForm>
  </div>
</template>
