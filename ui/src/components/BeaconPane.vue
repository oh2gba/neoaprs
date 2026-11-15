<script setup lang="ts">
// The My station tab: the settings the beacon and the status are made from (our station and where its position comes from, the beacon, the status), which apply as they are changed like the Settings tab's. Under the Beacon choice are the state of the beacon (BeaconStatus: the radio's
// status row; for a fixed station when the last beacon went and when the next is due, for a moving one the GPS and what SmartBeaconing does) and the row Beacon now (SendRow); under the Status choice, while a status is chosen, the status report as a row (StatusReportRow), and the row Send status now at the end of the Status group.
// useSendNow says when the buttons are on and asks twice; both are off, with a tip that says why, while the transmitter is off (RX only).
// While several radios are on, the Beacon choice is followed by Send on, a tick for each radio that is on (`radio/<id>/beacon`, applied at once; the last tick that is ticked is greyed, so that the beacon is switched off by
// the interval alone; with none ticked the main radio's is, for the beacon goes out on it), and the status row says each radio's beacon behind its arrow. Beacon now goes on the radios the beacon goes out on and is on while one of them is connected; Send status now goes on the main radio and is
// on while it is; each is off with the radios that are not connected as its title. With one radio on, the tab is as it was.
import BeaconStatus from "@/components/BeaconStatus.vue";
import SendRow from "@/components/SendRow.vue";
import StatusReportRow from "@/components/StatusReportRow.vue";
import TabHelp from "@/components/TabHelp.vue";
import type { Picked } from "@/composables/usePositionPick";
import SettingsForm from "@/components/SettingsForm.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { useSendNow, type SendKey } from "@/composables/useSendNow";
import { rxOnlyReason, tncNotConnected } from "@/lib/compose";
import { beaconOff } from "@/lib/beaconoff";
import { beaconRadios, followRadioValues, notConnectedWhy, radioValueOf, sendOnTicks, type SendOnTick } from "@/lib/beaconstatus";
import { fieldId, type PageRadio } from "@/lib/radios";
import { statusSource } from "@/lib/status";
import { computed, shallowRef, toRef, watch } from "vue";

const props = withDefaults(defineProps<{ picking?: boolean; picked?: Picked | null }>(), { picking: false, picked: null });
const emit = defineEmits<{ pickPosition: [] }>();

const { status, connected, now, config, send, settings, gps, receiveOnly } = useDaemonContext();
const radios = useRadios();
const several = computed(() => radios.severalSenders.value);
/** The radios Beacon now and the timer send on; with one radio on, that one. */
const beaconOn = computed(() => beaconRadios(radios.senders.value, radios.main.value));
/** A radio Beacon now would send on is connected (with one radio on, the page's link to it says it, as before). */
const beaconUp = computed(() => !several.value || beaconOn.value.some((radio) => radio.connected));
/** The main radio, which Send status now goes on, is connected (the same with one radio on). */
const statusUp = computed(() => !several.value || (radios.main.value?.connected ?? false));
/** The button that waits for its second press: its radio dropping forgets the press, as the link dropping does. */
const armedOf = shallowRef<() => SendKey | null>(() => null);
const linked = computed(() => {
  if (!several.value) return connected.value;
  const armed = armedOf.value();
  return armed === "beacon" ? beaconUp.value : armed === "status" ? statusUp.value : beaconUp.value || statusUp.value;
});
const sending = useSendNow(linked, settings.saving, toRef(props, "picking"), () => emit("pickPosition"));
armedOf.value = () => sending.armed.value;
/** Why a button that sends is off: RX only, a save on its way, its radios not connected; undefined while it is on. Beacon now and Send status now send while the beacon is Off (that is only no automatic beacon). */
function why(up: boolean, on: readonly PageRadio[]): string | undefined {
  if (receiveOnly.value) return rxOnlyReason();
  if (sending.why.value !== undefined) return sending.why.value;
  if (!several.value) return connected.value ? undefined : tncNotConnected();
  return up ? undefined : notConnectedWhy(on);
}
const beaconReady = computed(() => sending.ready.value && !receiveOnly.value && beaconUp.value);
const statusReady = computed(() => sending.ready.value && !receiveOnly.value && statusUp.value);
const beaconWhy = computed(() => why(beaconUp.value, beaconOn.value));
const statusWhy = computed(() => why(statusUp.value, radios.main.value === null ? [] : [radios.main.value]));
/** Each radio's beacon behind the status row's arrow, while several radios are on; until the daemon has told the radios, the status says the beacons, as it did. */
const beaconLines = computed(() =>
  several.value && radios.told.value
    ? beaconOn.value.map((radio) => ({ name: radio.name, beacon: radio.row.beacon, smart: radio.row.allowed.smart_beacon }))
    : [],
);

/** Send on as it is being set: a tick sent waits for the daemon as its draft, and shows the value in force else. */
function ticked(key: string, radio: PageRadio): boolean {
  const draft = settings.draft[key];
  const text = draft === "true" || draft === "false" ? draft : (radioValueOf(config.value, key) ?? String(radio.row.choices.beacon));
  return text === "true";
}
const ticks = computed<SendOnTick[]>(() => (several.value ? sendOnTicks(radios.senders.value, ticked, radios.main.value) : []));
/** The daemon's refusal of a tick, under the row. */
const tickError = computed(() => ticks.value.map((tick) => settings.errors[tick.key] ?? "").find((text) => text !== "") ?? "");
watch(
  () => Object.fromEntries(ticks.value.flatMap((tick) => [[tick.key, radioValueOf(config.value, tick.key) ?? ""]])),
  (inForce, before) => followRadioValues(settings.draft, settings.values.value, inForce, before),
);
/** A tick applies at once; the one ticked only because the beacon went out on it stays ticked, as it was seen. The row has one line for a refusal: a new tick takes the old one away. */
function tick(key: string, event: Event): void {
  if (!(event.target instanceof HTMLInputElement)) return;
  for (const one of ticks.value) delete settings.errors[one.key];
  const held = ticks.value.filter((one) => one.held && one.key !== key).map((one): [string, string] => [one.key, "true"]);
  settings.change({ ...Object.fromEntries(held), [key]: event.target.checked ? "true" : "false" });
}
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
          <div v-if="ticks.length > 0" class="field" :class="{ invalid: tickError !== '' }" role="group" aria-labelledby="beacon-send-on">
            <span id="beacon-send-on" class="field-label">{{ t("radio.send_on") }}</span>
            <div class="field-control toolbar-checks">
              <label v-for="one in ticks" :key="one.key" class="check">
                <input :id="`set-${fieldId(one.key)}`" type="checkbox" :checked="one.on" :disabled="one.last" @change="tick(one.key, $event)" />{{ one.name }}
              </label>
            </div>
            <p v-if="tickError" class="field-error" role="alert">{{ tickError }}</p>
          </div>
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
          <StatusReportRow
            :text="status?.station_status ?? ''"
            :last-sent="status?.station_status_last_sent ?? null"
            :minutes="config?.values['status/interval_min'] ?? ''"
            :rig="status?.rig_state ?? 'unused'"
            :beacon-off="beaconOff(config?.values ?? {})"
            :rx-only="receiveOnly"
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
