<script setup lang="ts">
// The Beacon tab: the settings the beacon and the status are made from (our station and where its position comes from, the beacon, the status), which apply as they are changed like the Settings tab's, with a preview, closed until asked for, of the packet those values would make and,
// for a status that is a text of our own, of the status report. The buttons that send now are where their words are: the beacon status at the top of the tab (BeaconStatus: for a fixed station when the last beacon went and when the next is due, for a moving one the GPS and what SmartBeaconing does,
// with Beacon now), and, while there is a status, the status last sent with Send status now at the top of the Status group (SendRow). useSendNow says when they are on and asks twice; both are off, with a tip that says the beacon is off, while the beacon is Off.
import BeaconStatus from "@/components/BeaconStatus.vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import SendRow from "@/components/SendRow.vue";
import type { Picked } from "@/composables/usePositionPick";
import SettingsForm from "@/components/SettingsForm.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useSendNow } from "@/composables/useSendNow";
import { beaconText, statusText } from "@/lib/beacon";
import { NONE } from "@/lib/format";
import { beaconOff } from "@/lib/beaconoff";
import { statusSource } from "@/lib/status";
import { computed, toRef } from "vue";

const props = withDefaults(defineProps<{ picking?: boolean; picked?: Picked | null }>(), { picking: false, picked: null });
const emit = defineEmits<{ pickPosition: [] }>();

const { status, connected, now, config, send, settings, gps } = useDaemonContext();
const sending = useSendNow(connected, settings.saving, toRef(props, "picking"), () => emit("pickPosition"));
/** Whether there is a status to send: what is saved says so, not what is being typed. */
const statusOn = computed(() => config.value !== null && statusSource(config.value.values) !== "off");
/** The beacon is Off (what is saved says so): neither button sends anything, and the tip says why. */
const off = computed(() => config.value !== null && beaconOff(config.value.values));
const ready = computed(() => sending.ready.value && !off.value);
const why = computed(() => (off.value ? t("beacon.off_why") : sending.why.value));

const current = computed(() => {
  const text = status.value?.station_status ?? "";
  const rig = status.value?.rig_state ?? "unused";
  return `${text === "" ? NONE : text}${rig === "unused" ? "" : ` · ${t(rig === "on" ? "beacon.rigctld_on" : "beacon.rigctld_off")}`}`;
});
</script>

<template>
  <div class="beaconpane">
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
      <template #status>
        <SendRow
          v-if="statusOn"
          :label="t('beacon.status')"
          :text="current"
          :button="t('beacon.send_status_now')"
          :armed="sending.armed.value === 'status'"
          :disabled="!ready"
          :why="why"
          @press="sending.press('status', () => send({ cmd: 'status_now' }))"
        />
      </template>
      <template #preview="{ draft }">
        <DisclosureBox
          plain
          class="beacon-preview"
          :title="beaconText(draft) ? t('beacon.preview') : t('beacon.preview_empty')"
          :summary-class="{ problem: !beaconText(draft) }"
        >
          <div class="beacon-preview-body">
            <span class="muted">{{ t("beacon.packet") }}</span>
            <code v-if="beaconText(draft)" class="mono" :aria-label="t('beacon.packet_label')">{{ beaconText(draft) }}</code>
            <template v-if="statusText(draft, new Date(now))">
              <span class="muted">{{ t("beacon.status") }}</span>
              <code class="mono" :aria-label="t('beacon.status_label')">{{ statusText(draft, new Date(now)) }}</code>
            </template>
          </div>
        </DisclosureBox>
      </template>
    </SettingsForm>
  </div>
</template>
