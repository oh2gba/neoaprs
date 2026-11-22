<script setup lang="ts">
// The status of the Digipeater group in Settings, under its tickbox while ticked: a status row
// (StatusFold.vue) with the words of lib/digistatus.ts. One per radio's Enable (`tnc`) and one
// per pair of radios that is on (`pair`), with the counts of each way and the held frames behind
// the arrow.
import { computed, inject } from "vue";
import StatusFold from "@/components/StatusFold.vue";
import { DAEMON_KEY } from "@/composables/useDaemonContext";
import { digiLook, pairLook, type PairLink } from "@/lib/digistatus";
import { rxOnlyLink } from "@/lib/settinglink";
import type { RadioRow } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{ tnc?: Pick<RadioRow, "stats"> | null; pair?: PairLink; startedAt?: string | null; now?: number; rxOnly?: boolean }>(),
  {
    tnc: null,
    pair: undefined,
    startedAt: undefined,
    now: undefined,
    rxOnly: undefined,
  },
);
const context = inject(DAEMON_KEY, null);
/** The daemon start time and RX only as given, else the page's. */
const startedAt = computed(() => (props.startedAt === undefined ? (context?.status.value?.started_at ?? null) : props.startedAt));
const now = computed(() => props.now ?? context?.now.value ?? Date.now());
const rxOnly = computed(() => props.rxOnly ?? context?.settings.draft["station/transmit"] === "false");
/** The row text and its lines behind the arrow, each only when it has content. */
const look = computed(() => {
  if (props.pair !== undefined) {
    const pair = pairLook(props.pair, startedAt.value, now.value, rxOnly.value);
    return { ...pair, lines: [pair.since, pair.ways, ...pair.held, ...pair.tooLong].filter((line) => line !== "") };
  }
  if (props.tnc === null) return null;
  const tnc = digiLook(props.tnc, startedAt.value, now.value, rxOnly.value);
  return { ...tnc, lines: [tnc.since, tnc.held].filter((line) => line !== "") };
});
</script>

<template>
  <StatusFold v-if="look" class="digistatus" :state="look.state" :tone="look.tone" :line="look.line" :link="rxOnly ? rxOnlyLink() : undefined">
    <p v-for="(line, i) in look.lines" :key="i" class="igatefold">{{ line }}</p>
  </StatusFold>
</template>
