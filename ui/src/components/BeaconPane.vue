<script setup lang="ts">
// The Beacon tab: the beacon box on top (the last and the next beacon, "Beacon now"), and under it the settings the beacon is made from (the beacon's own and our station's: call, position, symbol,
// comment, status), saved as the Settings tab saves, with a preview of the packet those values would make and, when the static status is not empty, of the status report it makes.
import BeaconBox from "@/components/BeaconBox.vue";
import type { Picked } from "@/composables/usePositionPick";
import SettingsForm from "@/components/SettingsForm.vue";
import type { Toast } from "@/composables/useDaemon";
import { beaconText, statusText } from "@/lib/beacon";
import type { Command, ConfigValues, StatusMessage } from "@/protocol/protocol";

defineProps<{
  status: StatusMessage | null;
  connected: boolean;
  now: number;
  config: ConfigValues | null;
  lastError: Toast | null;
  send: (command: Command) => boolean;
  picking?: boolean;
  picked?: Picked | null;
}>();
const emit = defineEmits<{ beacon: []; pickPosition: [] }>();
</script>

<template>
  <div class="beaconpane">
    <BeaconBox :status="status" :connected="connected" :now="now" @send="emit('beacon')" />
    <SettingsForm
      :config="config"
      :last-error="lastError"
      :send="send"
      scope="beacon"
      :picking="picking"
      :picked="picked"
      @pick-position="emit('pickPosition')"
    >
      <template #preview="{ draft }">
        <div class="beacon-preview">
          <span class="muted">Packet</span>
          <code v-if="beaconText(draft)" class="mono" aria-label="The beacon as it would be sent">{{ beaconText(draft) }}</code>
          <span v-else class="problem">These values make no packet yet.</span>
          <template v-if="statusText(draft, new Date(now))">
            <span class="muted">Status</span>
            <code class="mono" aria-label="The static status report as it would be sent">{{ statusText(draft, new Date(now)) }}</code>
          </template>
        </div>
      </template>
    </SettingsForm>
  </div>
</template>
