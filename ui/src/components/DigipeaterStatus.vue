<script setup lang="ts">
// The status of the Digipeater group of the Settings tab, under its tickbox and only while it is ticked: the radio's status row (StatusFold.vue) with the words of lib/digistatus.ts, and behind its arrow since when the count runs and the frames the burst limit held back.
// One under each radio's Enable, with that radio's counts (`tnc`: its row; nothing while they are not told, null), and one under the Call of each pair of radios that is on (`pair`: its two radios with their counts), with
// what went each way and what was held back or too long for each radio behind the arrow. When the daemon started, the time and whether RX only is ticked are the page's unless they are given.
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
/** When the daemon started, the time and RX only, as given, else the page's (RX only as the form holds it). */
const startedAt = computed(() => (props.startedAt === undefined ? (context?.status.value?.started_at ?? null) : props.startedAt));
const now = computed(() => props.now ?? context?.now.value ?? Date.now());
const rxOnly = computed(() => props.rxOnly ?? context?.settings.draft["station/transmit"] === "false");
/** What the row says, and its lines behind the arrow, each only when it has something: a pair's since, each way, held and too long; a radio's since and the burst's held. */
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
