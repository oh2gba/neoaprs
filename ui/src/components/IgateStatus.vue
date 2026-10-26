<script setup lang="ts">
// The status of the Internet group of the Settings tab: one quiet line (lib/igatestatus.ts), as the radio status has under the TNC group. The state as a mark is in the top bar of the page, not here.
import { computed } from "vue";
import { igateStatus } from "@/lib/igatestatus";
import type { IgateState } from "@/protocol/protocol";

const props = defineProps<{ igate: IgateState; values: Readonly<Record<string, string>> }>();
const line = computed(() => igateStatus(props.igate, props.values));
</script>

<template>
  <p class="tncstatus igatestatus" role="status">{{ line }}</p>
</template>
