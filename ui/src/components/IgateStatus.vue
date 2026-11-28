<script setup lang="ts">
// The status of the Internet (APRS-IS) group in Settings, shown under its tickboxes while either is
// ticked and its room kept while neither is (SettingsForm.vue): a status row (StatusFold.vue) with
// the words of lib/igatestatus.ts and the server, the filter and what was sent behind its arrow.
import { computed, ref } from "vue";
import IgateSent from "@/components/IgateSent.vue";
import StatusFold from "@/components/StatusFold.vue";
import { igateLook } from "@/lib/igatestatus";
import type { IgateState } from "@/protocol/protocol";

const props = defineProps<{ igate: IgateState; values: Readonly<Record<string, string>>; stations: number }>();
const open = ref(false);
const look = computed(() => igateLook(props.igate, props.values, props.stations));
</script>

<template>
  <StatusFold class="igatestatus" :state="look.state" :tone="look.tone" :line="look.line" @folded="open = $event">
    <p class="igatefold">{{ look.server }}</p>
    <p v-if="look.filter" class="igatefold">{{ look.filter }}</p>
    <p v-if="look.sent" class="igatefold">{{ look.sent }}</p>
    <IgateSent v-if="igate.gate" :open="open" />
  </StatusFold>
</template>
