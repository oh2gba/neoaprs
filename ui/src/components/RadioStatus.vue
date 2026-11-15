<script setup lang="ts">
// The status row of a radio in the Radio group of the Settings tab (the box of each radio): one line in view (the StatusFold every group's status is), the state of the radio link as a word and plain words (lib/tncstatus.ts: what it is connected to and when a packet last came, that it is searching for the radio, or why it is not connected;
// the counters are its hover title). There is no Reconnect: the radio is found again by itself (the daemon retries, probes a silent radio and follows an adapter that comes back as another port). An arrow in front opens what is behind it: the fields of the radio (the
// default slot) and the Terminal (TncTerminal.vue). The Dummy radio is a muted pill and a line that says nothing goes on the air.
// The fold is closed unless the radio is not connected (`open`, which opens it when it turns true later and never closes it).
import { computed } from "vue";
import StatusFold from "@/components/StatusFold.vue";
import TncTerminal from "@/components/TncTerminal.vue";
import { useRadios } from "@/composables/useRadios";
import { rowPillClass, rowPillText, rowStatus, statsCounts } from "@/lib/tncstatus";
import type { RadioRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ row: RadioRow; now: number; open?: boolean }>(), { open: false });
const radios = useRadios(); // (a device another radio holds is said by that radio's name, as the page calls it)

/** What the row of the status says, from the radio's row. */
const look = computed(() => ({
  state: rowPillText(props.row),
  tone: rowPillClass(props.row),
  line: rowStatus(props.row, props.now, radios),
  hover: statsCounts(props.row.stats),
}));
</script>

<template>
  <StatusFold class="radiostatus" :state="look.state" :tone="look.tone" :line="look.line" :hover="look.hover" :open="open">
    <slot></slot>
    <TncTerminal :tnc="row" />
  </StatusFold>
</template>
