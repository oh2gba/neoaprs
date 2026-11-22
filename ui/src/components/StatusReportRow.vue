<script setup lang="ts">
// Status report row under the Status choice of the My station tab: a StatusFold with the words
// of lib/statusreport.ts. Behind the arrow: the current status, how often it is sent, the line
// of each radio when several are on (`radios`), and whether rigctld answers when the status is
// the radio's. Off in the warn colour in RX only. Send status now is SendRow.vue.
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
    /** the line of each radio the status goes out on while several are on; none while one is */
    radios?: readonly string[];
  }>(),
  { radios: () => [], sentNowhere: false },
);
const look = computed(() =>
  reportLook(props.lastSent, props.minutes, props.beaconOff, props.rxOnly, props.sentNowhere, props.now),
);
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
