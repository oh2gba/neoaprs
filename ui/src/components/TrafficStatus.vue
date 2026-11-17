<script setup lang="ts">
// The status of the group Ships (AIS) or Aircraft (ADS-B) of the Settings tab, under its tickbox and only while it is ticked (in the form's values, `draft`): the radio's status row (StatusFold.vue) with the words of lib/traffic.ts
// (receiving, and how many within how many km; waiting for a position; not reachable, and why), and behind its arrow when it was read last and whose data it is.
import { computed } from "vue";
import StatusFold from "@/components/StatusFold.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { feedLook } from "@/lib/traffic";

const props = defineProps<{ feed: "ais" | "adsb"; draft: Readonly<Record<string, string>> }>();
const { traffic } = useDaemonContext();
const look = computed(() =>
  traffic.value === null || props.draft[`${props.feed}/enabled`] !== "true" ? null : feedLook(props.feed, traffic.value[props.feed]),
);
</script>

<template>
  <StatusFold v-if="look" class="trafficstatus" :state="look.state" :tone="look.tone" :line="look.line">
    <p v-if="look.updated" class="igatefold">{{ look.updated }}</p>
    <p class="igatefold">{{ look.licence }}</p>
  </StatusFold>
</template>
