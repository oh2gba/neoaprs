<script setup lang="ts">
// The status row of a radio in the Radio group: the link state as a word and plain text
// (lib/tncstatus.ts), with the counters as the hover title. A connected radio's line is split in
// parts so that the row keeps its height. The fold holds the default slot and, for types that
// have one, the terminal. The fold starts closed unless the radio is not connected.
import { computed } from "vue";
import StatusFold from "@/components/StatusFold.vue";
import TncTerminal from "@/components/TncTerminal.vue";
import { useRadios } from "@/composables/useRadios";
import { rowParts, rowPillClass, rowPillText, rowStatus, statsCounts } from "@/lib/tncstatus";
import type { RadioRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ row: RadioRow; now: number; open?: boolean }>(), { open: false });
const radios = useRadios();

/** What the row says, from the radio's row. */
const look = computed(() => {
  const parts = rowParts(props.row, props.now);
  const line = rowStatus(props.row, props.now, radios);
  const counts = statsCounts(props.row.stats);
  return {
    state: rowPillText(props.row),
    tone: rowPillClass(props.row),
    line,
    parts,
    hover: parts === null ? counts : `${line}\n${counts}`,
  };
});
</script>

<template>
  <StatusFold
    class="radiostatus"
    :state="look.state"
    :tone="look.tone"
    :line="look.line"
    :hover="look.hover"
    :parts="look.parts"
    :open="open"
  >
    <slot></slot>
    <TncTerminal v-if="row.can.terminal" :tnc="row" />
  </StatusFold>
</template>
