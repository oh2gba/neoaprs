<script setup lang="ts">
// The status row of a radio in the Radio group of the Settings tab (the box of each radio): one line in view (the StatusFold every group's status is), the state of the radio link as a word and plain words (lib/tncstatus.ts: what it is connected to and when a packet last came, that it is searching for the radio, or why it is not connected;
// the counters are its hover title). There is no Reconnect: the radio is found again by itself (the daemon retries, probes a silent radio and follows an adapter that comes back as another port). An arrow in front opens what is behind it: the ports a search listens to, the problem when the line does not already say it, the fields of the radio (the
// default slot) and the Terminal (TncTerminal.vue). The Dummy radio is a muted pill and a line that says nothing goes on the air.
// A radio of before (radio 1 the FM radio, radio 2 the HF radio) is told by its topic (`tnc`, `hf`); any other by its row of the topic `radios` (`row`), in the same words.
// The fold is closed unless the radio is not connected (`open`, which opens it when it turns true later and never closes it). Before the daemon has told the state of the radio the fields are there without the line.
import { computed } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import StatusFold from "@/components/StatusFold.vue";
import TncTerminal from "@/components/TncTerminal.vue";
import { t } from "@/i18n";
import { pillClass, pillText, rowPillClass, rowPillText, rowStatus, searchedPorts, statsCounts, tncCounts, tncStatus } from "@/lib/tncstatus";
import type { RadioRow, TncState } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ tnc: TncState | null; row?: RadioRow | null; now: number; open?: boolean }>(), { row: null, open: false });

/** What the row of the status says: from the radio's topic of before, else from its row. */
const look = computed(() => {
  const { tnc, row } = props;
  if (tnc !== null) {
    const line = tncStatus(tnc, props.now);
    return {
      state: pillText(tnc),
      tone: pillClass(tnc),
      line,
      hover: tncCounts(tnc),
      ports: searchedPorts(tnc),
      problem: tnc.problem !== "" && !line.includes(tnc.problem) ? tnc.problem : "",
      lines: tnc,
    };
  }
  if (row === null) return null;
  return {
    state: rowPillText(row),
    tone: rowPillClass(row),
    line: rowStatus(row, props.now),
    hover: statsCounts(row.stats),
    ports: null,
    problem: "",
    lines: row,
  };
});
</script>

<template>
  <StatusFold v-if="look" class="radiostatus" :state="look.state" :tone="look.tone" :line="look.line" :hover="look.hover" :open="open">
    <DisclosureBox v-if="look.ports" :title="t('settings.tnc.ports')">
      <ul class="tncports mono">
        <li v-for="port in look.ports" :key="port">{{ port }}</li>
      </ul>
    </DisclosureBox>
    <p v-if="look.problem" class="problem" role="status">{{ look.problem }}</p>
    <slot></slot>
    <TncTerminal :tnc="look.lines" />
  </StatusFold>
  <slot v-else></slot>
</template>
