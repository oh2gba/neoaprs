<script setup lang="ts">
// The status report as a row under the Status choice of the My station tab: the radio's status row (StatusFold.vue) with the words of lib/statusreport.ts, when the last report went and when the next may, and behind the arrow what the radio's status is now (a text of our own is the Text field above), how
// often it is sent, while several radios are on the status on each radio it goes out on (`radios`: "HF: last sent 2 min ago · next in 28 min (every 30 min)", as the beacon's row says each radio's beacon), and, when the
// status is the radio's, whether rigctld answers. In RX only the row is off in the warn colour. Send status now is a row of its own (SendRow.vue).
import { computed } from "vue";
import StatusFold from "@/components/StatusFold.vue";
import { t } from "@/i18n";
import { dateTimeText } from "@/lib/format";
import { rxOnlyLink } from "@/lib/settinglink";
import { reportLook } from "@/lib/statusreport";
import { every } from "@/lib/settingchoices";

const props = withDefaults(
  defineProps<{
    /** the text last sent, shown behind the arrow while it comes from the radio */
    text: string;
    lastSent: string | null;
    minutes: string;
    rig: "off" | "on" | "unused";
    beaconOff: boolean;
    rxOnly: boolean;
    /** the status is ticked for no radio that is on: nothing can send it */
    sentNowhere?: boolean;
    now: number;
    /** the line of each radio the status goes out on while several radios are on; none while one is */
    radios?: readonly string[];
  }>(),
  { radios: () => [], sentNowhere: false },
);
const look = computed(() => reportLook(props.lastSent, props.minutes, props.beaconOff, props.rxOnly, props.sentNowhere, props.now));
</script>

<template>
  <StatusFold
    class="beaconstatus"
    :state="look.state"
    :tone="look.tone"
    :line="look.line"
    :hover="lastSent === null ? undefined : dateTimeText(lastSent)"
    :link="rxOnly ? rxOnlyLink() : undefined"
  >
    <p v-if="rig !== 'unused' && text !== ''" class="igatefold">{{ text }}</p>
    <p v-if="minutes !== ''" class="igatefold">{{ every(minutes) }}</p>
    <p v-for="line in radios" :key="line" class="igatefold">{{ line }}</p>
    <p v-if="rig !== 'unused'" class="igatefold">{{ t(rig === "on" ? "beacon.rigctld_on" : "beacon.rigctld_off") }}</p>
  </StatusFold>
</template>
