<script setup lang="ts">
// The beacon status at the top of the Beacon tab, in the look of the radio status of the Settings tab (components/RadioStatus.vue): a label, one coloured pill and plain lines, with Beacon now at the end of the first line. A fixed station says when
// the last beacon went and when the timer sends the next; a moving station says the GPS (the pill is its state, the line the fix) and under it what SmartBeaconing does, or "Beacon off" while the beacon is Off (the GPS is shown all the same, so that the fix can be watched), and, when there is no fix, why (the daemon's own line). The words are
// lib/beaconstatus.ts's; what Beacon now does when it is pressed, and when it is on, is the tab's (useSendNow).
import { computed } from "vue";
import SendButton from "@/components/SendButton.vue";
import { t } from "@/i18n";
import { beaconBlock } from "@/lib/beaconstatus";
import type { GpsState, StatusMessage } from "@/protocol/protocol";

const props = defineProps<{
  status: StatusMessage | null;
  gps: GpsState | null;
  /** the settings in force, key to text */
  values: Readonly<Record<string, string>>;
  now: number;
  armed: boolean;
  disabled: boolean;
  why?: string;
}>();
const emit = defineEmits<{ press: [] }>();
const block = computed(() => beaconBlock(props.status, props.gps, props.values, props.now));
</script>

<template>
  <div class="beaconstatus" :class="{ moving: block.moving }">
    <div class="beaconhead">
      <span class="beaconlabel">{{ block.label }}</span>
      <span v-if="block.pill" class="statepill" :class="block.pill.tone">{{ block.pill.text }}</span>
      <span class="tncstatus" role="status" :title="block.hover">{{ block.line }}</span>
      <SendButton :label="t('beacon.beacon_now')" :armed="armed" :disabled="disabled" :why="why" @press="emit('press')" />
    </div>
    <p v-if="block.smart" class="mobileline" role="status">{{ block.smart }}</p>
    <p v-if="block.problem" class="problem" role="status">{{ block.problem }}</p>
  </div>
</template>
