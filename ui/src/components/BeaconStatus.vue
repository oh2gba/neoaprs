<script setup lang="ts">
// The state of the beacon, as a row under the Beacon choice of the My station tab: the radio's status row (StatusFold.vue). A fixed station says on or off and when the last beacon went and when the timer sends the next; a moving station says the state of the GPS (fix, no fix) and the fix, and behind the arrow what SmartBeaconing does,
// why there is no fix, and the time of the last beacon. While the beacon is Off a fixed station says off ("Beacon off"), a moving one keeps showing the GPS so that the fix can be watched. The words are lib/beaconstatus.ts's. Beacon now is not here: it is a row of its own (SendRow.vue).
// While several radios are on (`radios`, the ones the beacon goes out on), a fixed station's line is the latest and the soonest of theirs, and behind the arrow is a line for each, by its name, with its own interval.
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
    /** the radios the beacon goes out on while several radios are on; none while one is */
    radios?: readonly BeaconRadio[];
    /** nothing is sent: RX only, or no radio that is on can send (the page's `receiveOnly`) */
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
