<script setup lang="ts">
// The My station tab: the settings the beacon and the status are made from (our station and where its position comes from, the beacon, the status), which apply as they are changed like the Settings tab's. Under the Beacon choice are the state of the beacon (BeaconStatus: the radio's
// status row; for a fixed station when the last beacon went and when the next is due, for a moving one the GPS and what SmartBeaconing does) and the row Beacon now (SendRow); under the Status choice, while a status is chosen, the status report as a row (StatusReportRow), and the row Send status now at the end of the Status group.
// useSendNow says when the buttons are on and asks twice; both are off, with a tip that says why, while the transmitter is off (RX only).
// While several radios are on, the Beacon choice is followed by Send on, a tick for each radio that is on (`radio/<id>/beacon`, applied at once; the last tick that is ticked is greyed, so that the beacon is switched off by
// the interval alone; none is ticked while the radios it was ticked for are off), and the status row says each radio's beacon behind its arrow. The Status choice is followed by the status's own Send on, the same
// row (SendOn.vue, `radio/<id>/status`), and its row says the status on each radio behind its arrow. Beacon now goes on
// the radios the beacon goes out on and Send status now on those the status goes out on, each on while one of them is connected and off with the radios that are not connected as its title. With one radio on, the tab is as it was.
import BeaconStatus from "@/components/BeaconStatus.vue";
import SendOn from "@/components/SendOn.vue";
import SendRow from "@/components/SendRow.vue";
import StatusReportRow from "@/components/StatusReportRow.vue";
import TabHelp from "@/components/TabHelp.vue";
import type { Picked } from "@/composables/usePositionPick";
import SettingsForm from "@/components/SettingsForm.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { useSendNow, type SendKey } from "@/composables/useSendNow";
import { useSendOn } from "@/composables/useSendOn";
import { rxOnlyReason, tncNotConnected } from "@/lib/compose";
import { beaconOff } from "@/lib/beaconoff";
import { beaconRadios, notConnectedWhy, statusRadios } from "@/lib/beaconstatus";
import type { PageRadio } from "@/lib/radios";
import { statusSource } from "@/lib/status";
import { statusRadioLines } from "@/lib/statusreport";
import { computed, shallowRef, toRef } from "vue";

const props = withDefaults(defineProps<{ picking?: boolean; picked?: Picked | null }>(), { picking: false, picked: null });
const emit = defineEmits<{ pickPosition: [] }>();

const { status, connected, now, config, send, settings, gps, receiveOnly } = useDaemonContext();
const radios = useRadios();
const several = computed(() => radios.severalSenders.value);
/** The radios Beacon now and the timer send on; with one radio on, that one. */
const beaconOn = computed(() => beaconRadios(radios.senders.value));
/** A radio Beacon now would send on is connected (a radio that only listens is none of them); until the daemon has told the radios, the page's link to any radio says it. */
const beaconUp = computed(() => (radios.told.value ? beaconOn.value.some((radio) => radio.connected) : connected.value));
/** The radios Send status now and the timer send the status on; with one radio on, that one. */
const statusOn = computed(() => statusRadios(radios.senders.value));
/** No status goes by the timer: the beacon is Off, or the status is ticked for no radio that is on (its row then says no timed status, as the beacon's says no timed beacon). */
const statusUntimed = computed(() => beaconOff(config.value?.values ?? {}) || (several.value && statusOn.value.length === 0));
/** A radio Send status now would send on is connected (the same until the radios are told). */
const statusUp = computed(() => (radios.told.value ? statusOn.value.some((radio) => radio.connected) : connected.value));
/** The button that waits for its second press: its radio dropping forgets the press, as the link dropping does. */
const armedOf = shallowRef<() => SendKey | null>(() => null);
const linked = computed(() => {
  const armed = armedOf.value();
  return armed === "beacon" ? beaconUp.value : armed === "status" ? statusUp.value : beaconUp.value || statusUp.value;
});
const sending = useSendNow(linked, settings.saving, toRef(props, "picking"), () => emit("pickPosition"));
armedOf.value = () => sending.armed.value;
/** Why a button that sends is off: RX only, a save on its way, its radios not connected; undefined while it is on. Beacon now and Send status now send while the beacon is Off (that is only no automatic beacon). */
function why(up: boolean, on: readonly PageRadio[]): string | undefined {
  if (receiveOnly.value) return rxOnlyReason();
  if (sending.why.value !== undefined) return sending.why.value;
  if (up) return undefined;
  return several.value ? notConnectedWhy(on) : tncNotConnected();
}
const beaconReady = computed(() => sending.ready.value && !receiveOnly.value && beaconUp.value);
const statusReady = computed(() => sending.ready.value && !receiveOnly.value && statusUp.value);
const beaconWhy = computed(() => why(beaconUp.value, beaconOn.value));
const statusWhy = computed(() => why(statusUp.value, statusOn.value));
/** Each radio's beacon behind the status row's arrow, while several radios are on; until the daemon has told the radios, the status says the beacons, as it did. */
const beaconLines = computed(() =>
  several.value && radios.told.value
    ? beaconOn.value.map((radio) => ({ name: radio.name, beacon: radio.row.beacon, smart: radio.row.allowed.smart_beacon }))
    : [],
);

/** The status on each radio it goes out on behind the status row's arrow, while several radios are on. */
const statusLines = computed(() =>
  several.value && radios.told.value
    ? statusRadioLines(
        statusOn.value.map((radio) => ({ name: radio.name, status: radio.row.status })),
        now.value,
      )
    : [],
);

/** The beacon's Send on and the status's: one row of ticks each, applied at once (composables/useSendOn.ts). */
const { ticks: beaconTicks, error: beaconTickError, tick: beaconTick } = useSendOn("beacon", radios);
const { ticks: statusTicks, error: statusTickError, tick: statusTick } = useSendOn("status", radios);
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
          <SendOn v-if="beaconTicks.length > 0" id="beacon-send-on" :ticks="beaconTicks" :error="beaconTickError" @tick="beaconTick" />
          <BeaconStatus :status="status" :gps="gps" :values="config?.values ?? {}" :now="now" :radios="beaconLines" :receive-only="receiveOnly" />
          <SendRow
            id="beacon-now"
            :label="t('beacon.now_label')"
            :tip-label="t('beacon.now_tip_label')"
            :tip="t('beacon.now_tip')"
            :button="t('beacon.beacon_now')"
            :armed="sending.armed.value === 'beacon'"
            :disabled="!beaconReady"
            :why="beaconWhy"
            @press="sending.press('beacon', () => send({ cmd: 'beacon_now' }))"
          />
        </template>
        <template v-else-if="fieldKey === 'status/source' && statusSource(draft) !== 'off'">
          <SendOn v-if="statusTicks.length > 0" id="status-send-on" :ticks="statusTicks" :error="statusTickError" @tick="statusTick" />
          <StatusReportRow
            :text="status?.station_status ?? ''"
            :last-sent="status?.station_status_last_sent ?? null"
            :minutes="config?.values['status/interval_min'] ?? ''"
            :rig="status?.rig_state ?? 'unused'"
            :beacon-off="statusUntimed"
            :rx-only="receiveOnly"
            :radios="statusLines"
            :now="now"
          />
        </template>
        <template v-else-if="(fieldKey === 'station/status' || fieldKey === 'status/template') && statusSource(draft) !== 'off'">
          <SendRow
            id="status-now"
            :label="t('beacon.now_label')"
            :tip-label="t('beacon.status_now_tip_label')"
            :tip="t('beacon.status_now_tip')"
            :button="t('beacon.send_status_now')"
            :armed="sending.armed.value === 'status'"
            :disabled="!statusReady"
            :why="statusWhy"
            @press="sending.press('status', () => send({ cmd: 'status_now' }))"
          />
        </template>
      </template>
    </SettingsForm>
  </div>
</template>
