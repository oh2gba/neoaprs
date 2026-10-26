<script setup lang="ts">
// The status of the Internet stations group of the Settings tab, under its tickbox and only while it is ticked: the radio's status row (StatusFold.vue) with the words of lib/igatestatus.ts, and behind its arrow the server and the filter. The state as a mark is in the top bar of the page.
import { computed } from "vue";
import StatusFold from "@/components/StatusFold.vue";
import { igateLook } from "@/lib/igatestatus";
import type { IgateState } from "@/protocol/protocol";

const props = defineProps<{ igate: IgateState; values: Readonly<Record<string, string>>; stations: number }>();
const look = computed(() => igateLook(props.igate, props.values, props.stations));
</script>

<template>
  <StatusFold class="igatestatus" :state="look.state" :tone="look.tone" :line="look.line">
    <p class="igatefold">{{ look.server }}</p>
    <p class="igatefold">{{ look.filter }}</p>
  </StatusFold>
</template>
