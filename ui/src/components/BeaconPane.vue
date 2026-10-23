<script setup lang="ts">
// The Beacon tab: the settings the beacon and the status are made from (our station, the beacon, the status), which apply as they are changed like the Settings tab's, with a preview, closed until asked for, of the packet those values would make and,
// for a status that is a text of our own, of the status report. The buttons that send now are in their groups: "Last beacon: 2 min ago" with Beacon now at the top of the Beacon group, and, while there is a status, the status last sent with Send status now at
// the top of the Status group (SendRow; useSendNow says when they are on and asks twice).
import DisclosureBox from "@/components/DisclosureBox.vue";
import SendRow from "@/components/SendRow.vue";
import type { Picked } from "@/composables/usePositionPick";
import SettingsForm from "@/components/SettingsForm.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useSendNow } from "@/composables/useSendNow";
import { beaconText, statusText } from "@/lib/beacon";
import { NONE, agoWords, dateTimeText } from "@/lib/format";
import { statusSource } from "@/lib/status";
import { computed, toRef } from "vue";

const props = withDefaults(defineProps<{ picking?: boolean; picked?: Picked | null }>(), { picking: false, picked: null });
const emit = defineEmits<{ pickPosition: [] }>();

const { status, connected, now, config, send, settings } = useDaemonContext();
const sending = useSendNow(connected, settings.saving, toRef(props, "picking"), () => emit("pickPosition"));
/** Whether there is a status to send: what is saved says so, not what is being typed. */
const statusOn = computed(() => config.value !== null && statusSource(config.value.values) !== "off");

// only when the last beacon went out, in words, the full time on hover; how often is the choice below
const lastAt = computed(() => status.value?.beacon_last_sent ?? null);
const last = computed(() => (lastAt.value === null ? "not yet" : agoWords(lastAt.value, now.value)));
const current = computed(() => {
  const text = status.value?.station_status ?? "";
  const rig = status.value?.rig_state ?? "unused";
  return `${text === "" ? NONE : text}${rig === "unused" ? "" : ` · rigctld ${rig}`}`;
});
</script>

<template>
  <div class="beaconpane">
    <SettingsForm scope="beacon" :picking="picking" :picked="picked" @pick-position="emit('pickPosition')">
      <template #beacon>
        <SendRow
          label="Last beacon"
          :text="last"
          :hover="lastAt === null ? undefined : dateTimeText(lastAt)"
          button="Beacon now"
          :armed="sending.armed.value === 'beacon'"
          :disabled="!sending.ready.value"
          :why="sending.why.value"
          @press="sending.press('beacon', () => send({ cmd: 'beacon_now' }))"
        />
      </template>
      <template #status>
        <SendRow
          v-if="statusOn"
          label="Status"
          :text="current"
          button="Send status now"
          :armed="sending.armed.value === 'status'"
          :disabled="!sending.ready.value"
          :why="sending.why.value"
          @press="sending.press('status', () => send({ cmd: 'status_now' }))"
        />
      </template>
      <template #preview="{ draft }">
        <DisclosureBox
          plain
          class="beacon-preview"
          :title="beaconText(draft) ? 'Preview' : 'Preview: these values make no packet yet'"
          :summary-class="{ problem: !beaconText(draft) }"
        >
          <div class="beacon-preview-body">
            <span class="muted">Packet</span>
            <code v-if="beaconText(draft)" class="mono" aria-label="The beacon as it would be sent">{{ beaconText(draft) }}</code>
            <template v-if="statusText(draft, new Date(now))">
              <span class="muted">Status</span>
              <code class="mono" aria-label="The status as it would be sent">{{ statusText(draft, new Date(now)) }}</code>
            </template>
          </div>
        </DisclosureBox>
      </template>
    </SettingsForm>
  </div>
</template>
