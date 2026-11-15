<script setup lang="ts">
// The status of the Digipeater group of the Settings tab, under its tickbox and only while it is ticked: the radio's status row (StatusFold.vue) with the words of lib/digistatus.ts, and behind its arrow since when the count runs and the frames the burst limit held back.
// One under each radio's Enable, with that radio's counts (`tnc`: the FM radio of before's topic, or another radio's row in its shape); nothing while they are not told (null). When the daemon started, the time and
// whether RX only is ticked are the page's unless they are given.
import { computed, inject } from "vue";
import StatusFold from "@/components/StatusFold.vue";
import { DAEMON_KEY } from "@/composables/useDaemonContext";
import { digiLook } from "@/lib/digistatus";
import { rxOnlyLink } from "@/lib/settinglink";
import type { TncState } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ tnc: TncState | null; startedAt?: string | null; now?: number; rxOnly?: boolean }>(), {
  startedAt: undefined,
  now: undefined,
  rxOnly: undefined,
});
const context = inject(DAEMON_KEY, null);
/** When the daemon started, the time and RX only, as given, else the page's (RX only as the form holds it). */
const startedAt = computed(() => (props.startedAt === undefined ? (context?.status.value?.started_at ?? null) : props.startedAt));
const now = computed(() => props.now ?? context?.now.value ?? Date.now());
const rxOnly = computed(() => props.rxOnly ?? context?.settings.draft["station/transmit"] === "false");
const look = computed(() => (props.tnc === null ? null : digiLook(props.tnc, startedAt.value, now.value, rxOnly.value)));
</script>

<template>
  <StatusFold v-if="look" class="digistatus" :state="look.state" :tone="look.tone" :line="look.line" :link="rxOnly ? rxOnlyLink() : undefined">
    <p v-if="look.since" class="igatefold">{{ look.since }}</p>
    <p v-if="look.held" class="igatefold">{{ look.held }}</p>
  </StatusFold>
</template>
