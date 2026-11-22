<script setup lang="ts">
// The status of the Internet stations group in Settings, shown under its tickbox while ticked: a
// status row (StatusFold.vue) with the words of lib/igatestatus.ts and the server and filter
// behind its arrow.
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
