<script setup lang="ts">
// Traffic of one station in its panel: the latest 50 packets it sent and messages we sent to it
// (lib/stationtraffic.ts), newest first, laid out as the Packets tab lines (PacketLines). The
// daemon is asked (`station_traffic`) when the panel opens; later packets are added as they
// arrive, none from APRS-IS while Internet stations is off. A directed query shows "waiting…",
// "answered" or "no answer" (after two minutes); the three words share the width of the longest.
// SNR follows the summary where the radio measured one. A timer wakes the list only when a
// query's two minutes are up.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import PacketLines from "@/components/PacketLines.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useElementWidth } from "@/composables/useElementWidth";
import { t } from "@/i18n";
import { PACKETS_TABLE } from "@/lib/layout";
import { readingText } from "@/lib/signal";
import { igateOn } from "@/lib/settings";
import { isTrafficOf, mergeTraffic, nextDeadline, queryState, trafficKey, type QueryState } from "@/lib/stationtraffic";
import type { PacketRow } from "@/protocol/protocol";

const props = defineProps<{ call: string }>();
const { send, packets, stationTrafficByCall, config } = useDaemonContext();

const root = ref<HTMLElement | null>(null);
const width = useElementWidth(root);
const stacked = computed(() => width.value > 0 && width.value < PACKETS_TABLE);

/** Packets of the station received while the panel shows it; kept here so that one falling out
 * of the topic's 200 stays listed. */
const live = ref(new Map<string, PacketRow>());
watch(
  () => props.call,
  (call) => {
    live.value = new Map();
    send({ cmd: "station_traffic", call });
  },
  { immediate: true },
);
watch(
  () => [...packets.values()].filter((row) => isTrafficOf(row, props.call)),
  (rows) => {
    const added = rows.filter((row) => !live.value.has(trafficKey(row)));
    if (added.length > 0) live.value = new Map([...live.value, ...added.map((row): [string, PacketRow] => [trafficKey(row), row])]);
  },
  { immediate: true },
);

const logged = computed(() => stationTrafficByCall.value.get(props.call)?.packets ?? []);
const rows = computed(() => mergeTraffic(live.value.values(), logged.value, igateOn(config.value?.values ?? {})));

/** The time the states are read at, moved on when a query's wait is over. */
const now = ref(Date.now());
let timer: ReturnType<typeof setTimeout> | undefined;
watch(
  [rows, now],
  () => {
    clearTimeout(timer);
    const due = nextDeadline(props.call, rows.value, now.value);
    if (due !== null) timer = setTimeout(() => (now.value = Date.now()), Math.max(0, due - Date.now()) + 50);
  },
  { immediate: true },
);
watch(rows, () => (now.value = Date.now()));
onBeforeUnmount(() => clearTimeout(timer));

/** The radio's measured SNR ("SNR −3 dB") for a packet the station sent; null if none. */
const heard = (row: PacketRow): string | null => (row.direction === "in" ? readingText(row) : null);

const STATES: readonly QueryState[] = ["waiting", "answered", "no_answer"];
const stateOf = (row: PacketRow): QueryState | null => queryState(row, props.call, rows.value, now.value);
</script>

<template>
  <div ref="root" class="stationtraffic">
    <PacketLines :rows="rows" :stacked="stacked" :empty="t('station.traffic.none')" :key-of="trafficKey">
      <template #note="{ row }">
        <span v-if="stateOf(row) !== null" class="querystate twowords" :class="`query-${stateOf(row)}`" :data-state="stateOf(row)"
          ><span v-for="state in STATES" :key="state" :class="{ 'twowords-off': state !== stateOf(row) }" :aria-hidden="state !== stateOf(row)">{{
            t(`station.traffic.${state}`)
          }}</span></span
        >
        <span v-if="heard(row) !== null" class="signalnote muted" data-signal-note>{{ ` · ${heard(row)}` }}</span>
      </template>
    </PacketLines>
  </div>
</template>
