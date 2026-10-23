<script setup lang="ts">
// The Beacon tab: the box on top with what the beacon and the status are doing and the buttons that send them now (BeaconBox), and under it the settings they are made from (our station, the beacon, the
// status), saved as the Settings tab saves, with a preview, closed until asked for, of the packet those values would make and, for a status that is a text of our own, of the status report.
import BeaconBox from "@/components/BeaconBox.vue";
import type { Picked } from "@/composables/usePositionPick";
import SettingsForm from "@/components/SettingsForm.vue";
import type { Toast } from "@/composables/useDaemon";
import { beaconText, statusText } from "@/lib/beacon";
import { statusSource } from "@/lib/status";
import type { Command, ConfigValues, StatusMessage } from "@/protocol/protocol";
import { computed, ref } from "vue";

const props = defineProps<{
  status: StatusMessage | null;
  connected: boolean;
  now: number;
  config: ConfigValues | null;
  lastError: Toast | null;
  send: (command: Command) => boolean;
  picking?: boolean;
  picked?: Picked | null;
}>();
const emit = defineEmits<{ beacon: []; status: []; pickPosition: [] }>();

const unsaved = ref(false);
/** Whether there is a status to send: what is saved says so, not what is being typed. */
const statusOn = computed(() => props.config !== null && statusSource(props.config.values) !== "off");
</script>

<template>
  <div class="beaconpane">
    <BeaconBox
      :status="status"
      :connected="connected"
      :now="now"
      :status-on="statusOn"
      :unsaved="unsaved"
      :picking="picking"
      @arm="emit('pickPosition')"
      @send="emit('beacon')"
      @send-status="emit('status')"
    />
    <SettingsForm
      :config="config"
      :last-error="lastError"
      :send="send"
      scope="beacon"
      :picking="picking"
      :picked="picked"
      @pick-position="emit('pickPosition')"
      @dirty="unsaved = $event"
    >
      <template #preview="{ draft }">
        <details class="beacon-preview">
          <summary :class="{ problem: !beaconText(draft) }">{{ beaconText(draft) ? "Preview" : "Preview: these values make no packet yet" }}</summary>
          <div class="beacon-preview-body">
            <span class="muted">Packet</span>
            <code v-if="beaconText(draft)" class="mono" aria-label="The beacon as it would be sent">{{ beaconText(draft) }}</code>
            <template v-if="statusText(draft, new Date(now))">
              <span class="muted">Status</span>
              <code class="mono" aria-label="The status as it would be sent">{{ statusText(draft, new Date(now)) }}</code>
            </template>
          </div>
        </details>
      </template>
    </SettingsForm>
  </div>
</template>
