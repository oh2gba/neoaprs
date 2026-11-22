<script setup lang="ts">
// The beacon state row under the Beacon choice of My station. A fixed station shows on or off
// with the last and next beacon; a moving one shows the GPS state and, behind the arrow, what
// SmartBeaconing does (words: lib/beaconstatus.ts). With several radios on (`radios`) the line
// is the latest and soonest of theirs and the fold lists each radio.
import { computed } from "vue";
import StatusFold from "@/components/StatusFold.vue";
import { beaconBlock, type BeaconRadio } from "@/lib/beaconstatus";
import { rxOnlyLink } from "@/lib/settinglink";
import type { GpsState, StatusMessage } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{
    status: StatusMessage | null;
    gps: GpsState | null;
    /** the settings in force, key to text */
    values: Readonly<Record<string, string>>;
    now: number;
    /** the radios the beacon goes out on while several are on; none with one */
    radios?: readonly BeaconRadio[];
    /** nothing is sent: RX only, or no radio that is on can send */
    receiveOnly?: boolean;
  }>(),
  { radios: () => [], receiveOnly: false },
);
const block = computed(() => beaconBlock(props.status, props.gps, props.values, props.now, props.radios, props.receiveOnly));
</script>

<template>
  <StatusFold
    v-if="block.pill"
    class="beaconstatus"
    :state="block.pill.text"
    :tone="block.pill.tone"
    :line="block.line"
    :hover="block.hover"
    :link="block.rxOnly ? rxOnlyLink() : undefined"
  >
    <p v-if="block.smart" class="igatefold" role="status">{{ block.smart }}</p>
    <p v-if="block.problem" class="problem" role="status">{{ block.problem }}</p>
    <p v-for="line in block.radios" :key="line" class="igatefold">{{ line }}</p>
    <p v-if="block.hover && block.radios.length === 0" class="igatefold">{{ block.hover }}</p>
  </StatusFold>
</template>
