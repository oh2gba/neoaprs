<script setup lang="ts">
// The traffic of one station in its panel of the Stations tab: the packets it sent and the messages we sent to it, newest first, the latest 50 (lib/stationtraffic.ts), as the lines of the Packets tab (PacketLines: the same
// columns, the same block of each packet when the panel is narrower than PACKETS_TABLE, the same detail under a line that is clicked). The daemon is asked for the station's packets in its log when the panel opens on it
// (`station_traffic`), and the packets that come after are added as they come; while Internet stations is off none from APRS-IS is shown. A directed query of ours says how it went after its summary: "waiting…", "answered"
// when the answer it asks for came from the station, "no answer" after two minutes; the three words take the room of the longest, so that the line does not move when the word changes. The clock wakes the list at the moment
// a query's two minutes are up, and not otherwise.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import PacketLines from "@/components/PacketLines.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useElementWidth } from "@/composables/useElementWidth";
import { t } from "@/i18n";
import { PACKETS_TABLE } from "@/lib/layout";
import { igateOn } from "@/lib/settings";
import { isTrafficOf, mergeTraffic, nextDeadline, queryState, trafficKey, type QueryState } from "@/lib/stationtraffic";
import type { PacketRow } from "@/protocol/protocol";

const props = defineProps<{ call: string }>();
const { send, packets, stationTrafficByCall, config } = useDaemonContext();

const root = ref<HTMLElement | null>(null);
const width = useElementWidth(root);
const stacked = computed(() => width.value > 0 && width.value < PACKETS_TABLE);

/** The packets of the station that came by the topic while the panel shows it: kept here, so that one that falls out of the 200 of the topic stays in the list. */
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
      </template>
    </PacketLines>
  </div>
</template>
