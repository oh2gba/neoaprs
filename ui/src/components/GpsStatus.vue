<script setup lang="ts">
// The GPS block at the top of the Mobile group of the Beacon tab, in the look of the radio status (components/RadioStatus.vue): a pill with the state of the GPS and one line of plain words (lib/gpsstatus.ts: that it is off, what it is connecting to, that
// there is no fix yet, the fix with its speed, course, altitude and satellites and how old it is, or that it was lost), and under it, when there is no fix, why (the daemon's own line). The GPS is read as soon as a source is chosen, whether
// the beacon follows it or not, so the block is there to see the fix before Mobile is turned on. Before the daemon has told the state of the GPS there is no block.
import { computed } from "vue";
import { t } from "@/i18n";
import { gpsProblem, gpsStateText, gpsStatus } from "@/lib/gpsstatus";
import type { GpsState } from "@/protocol/protocol";

const props = defineProps<{ gps: GpsState | null; values: Readonly<Record<string, string>>; now: number }>();
const line = computed(() => (props.gps === null ? "" : gpsStatus(props.gps, props.values, props.now)));
const problem = computed(() => (props.gps === null ? "" : gpsProblem(props.gps)));
</script>

<template>
  <div v-if="gps" class="gpsstatus">
    <div class="gpshead">
      <span class="gpslabel">{{ t("gps.label") }}</span>
      <span class="statepill" :class="`gps-${gps.state}`">{{ gpsStateText(gps.state) }}</span>
      <span class="tncstatus" role="status">{{ line }}</span>
    </div>
    <p v-if="problem" class="problem" role="status">{{ problem }}</p>
  </div>
</template>
