<script setup lang="ts">
// The status of the iGate group of the Settings tab, in the look of the radio status: the state as a pill and one line (lib/igatestatus.ts), with what was heard and not gated as the line's hover title. The daemon's own reason for a
// connection that is down is not repeated here: the line says what is missing, or that it is connecting; the reason is the title.
import { computed } from "vue";
import { igateCounts, igateStateText, igateStatus } from "@/lib/igatestatus";
import type { IgateState } from "@/protocol/protocol";

const props = defineProps<{ igate: IgateState; values: Readonly<Record<string, string>>; now: number }>();
const line = computed(() => igateStatus(props.igate, props.values, props.now));
</script>

<template>
  <div class="igatestatus">
    <span class="statepill" :class="`igate-${igate.state}`">{{ igateStateText(igate.state) }}</span>
    <span class="tncstatus" role="status" :title="igateCounts(igate)">{{ line }}</span>
  </div>
</template>
