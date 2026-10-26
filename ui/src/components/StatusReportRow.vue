<script setup lang="ts">
// The status report as a row under the Status choice of the Beacon tab: the radio's status row (StatusFold.vue) with the words of lib/statusreport.ts, when the last report went and when the next may, and behind the arrow what the radio's status is now (a text of our own is the Text field above), how
// often it is sent and, when the status is the radio's, whether rigctld answers. In RX only the row is off in the warn colour. Send status now is a row of its own (SendRow.vue).
import { computed } from "vue";
import StatusFold from "@/components/StatusFold.vue";
import { t } from "@/i18n";
import { dateTimeText } from "@/lib/format";
import { rxOnlyLink } from "@/lib/settinglink";
import { reportLook } from "@/lib/statusreport";
import { every } from "@/lib/settingchoices";

const props = defineProps<{
  /** the text last sent, shown behind the arrow while it comes from the radio */
  text: string;
  lastSent: string | null;
  minutes: string;
  rig: "off" | "on" | "unused";
  beaconOff: boolean;
  rxOnly: boolean;
  now: number;
}>();
const look = computed(() => reportLook(props.lastSent, props.minutes, props.beaconOff, props.rxOnly, props.now));
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
    <p v-if="rig !== 'unused'" class="igatefold">{{ t(rig === "on" ? "beacon.rigctld_on" : "beacon.rigctld_off") }}</p>
  </StatusFold>
</template>
