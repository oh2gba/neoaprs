<script setup lang="ts">
// The My station tab: station, position source, beacon and status settings, applied as they
// change. Beacon now and Send status now are off in RX only, with a tip saying why (useSendNow).
// While several radios are on, each of the beacon and status choices is followed by a Send on
// row of ticks (SendOn.vue); the last ticked radio is greyed, so the beacon is switched off by
// the interval alone.
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
/** Whether a radio Beacon now would send on is connected; a listening-only radio does not count. */
const beaconUp = computed(() => (radios.told.value ? beaconOn.value.some((radio) => radio.connected) : connected.value));
/** The radios Send status now and the timer send the status on; with one radio on, that one. */
const statusOn = computed(() => statusRadios(radios.senders.value));
/** No timed status: the beacon is Off, or the status is ticked for no radio that is on. */
const statusNowhere = computed(() => several.value && statusOn.value.length === 0);
const statusUntimed = computed(() => beaconOff(config.value?.values ?? {}) || statusNowhere.value);
/** Whether a radio Send status now would send on is connected. */
const statusUp = computed(() => (radios.told.value ? statusOn.value.some((radio) => radio.connected) : connected.value));
/** The armed button: its radio dropping, like the link dropping, cancels the second press. */
const armedOf = shallowRef<() => SendKey | null>(() => null);
const linked = computed(() => {
  const armed = armedOf.value();
  return armed === "beacon" ? beaconUp.value : armed === "status" ? statusUp.value : beaconUp.value || statusUp.value;
});
const sending = useSendNow(linked, settings.saving, toRef(props, "picking"), () => emit("pickPosition"));
armedOf.value = () => sending.armed.value;
/** Why a sending button is off (RX only, a save pending, no radio connected); undefined when on. */
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
/** Each radio's beacon behind the status row's arrow, while several radios are on. */
const beaconLines = computed(() =>
  several.value && radios.told.value
    ? beaconOn.value.map((radio) => ({ name: radio.name, beacon: radio.row.beacon, smart: radio.row.allowed.smart_beacon }))
    : [],
);

/** The status on each radio behind the status row's arrow, while several radios are on. */
const statusLines = computed(() =>
  several.value && radios.told.value
    ? statusRadioLines(
        statusOn.value.map((radio) => ({ name: radio.name, status: radio.row.status })),
        now.value,
      )
    : [],
);

/** The beacon's and the status's Send on: a row of ticks each, applied at once (useSendOn.ts). */
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
            :sent-nowhere="statusNowhere"
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
