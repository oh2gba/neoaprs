<script setup lang="ts">
// The status report as a row under the Status choice of the Beacon tab: the radio's status row (StatusFold.vue), on in the ok colour, the status text that is sent as the line, and behind the arrow how often it is sent and, when the status is the radio's, whether rigctld answers. Send status now is a row of its own (SendRow.vue).
import StatusFold from "@/components/StatusFold.vue";
import { t } from "@/i18n";
import { every } from "@/lib/settingchoices";

defineProps<{ text: string; minutes: string; rig: "off" | "on" | "unused" }>();
</script>

<template>
  <StatusFold class="beaconstatus" :state="t('beacon.state.on')" tone="beacon-on" :line="text">
    <p v-if="minutes !== ''" class="igatefold">{{ every(minutes) }}</p>
    <p v-if="rig !== 'unused'" class="igatefold">{{ t(rig === "on" ? "beacon.rigctld_on" : "beacon.rigctld_off") }}</p>
  </StatusFold>
</template>
