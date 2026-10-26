<script setup lang="ts">
// The status of the Digipeater group of the Settings tab, under its tickbox and only while it is ticked: the radio's status row (StatusFold.vue) with the words of lib/digistatus.ts, and behind its arrow since when the count runs and the frames the burst limit held back.
import { computed } from "vue";
import StatusFold from "@/components/StatusFold.vue";
import { digiLook } from "@/lib/digistatus";
import type { TncState } from "@/protocol/protocol";

const props = defineProps<{ tnc: TncState; startedAt: string | null; now: number; rxOnly: boolean }>();
const look = computed(() => digiLook(props.tnc, props.startedAt, props.now, props.rxOnly));
</script>

<template>
  <StatusFold class="digistatus" :state="look.state" :tone="look.tone" :line="look.line">
    <p v-if="look.since" class="igatefold">{{ look.since }}</p>
    <p v-if="look.held" class="igatefold">{{ look.held }}</p>
  </StatusFold>
</template>
