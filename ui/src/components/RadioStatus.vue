<script setup lang="ts">
// The TNC group of the Settings tab: one line in view (the StatusFold every group's status is), the state of the radio link as a word and plain words (lib/tncstatus.ts: what it is connected to and when a packet last came, that it is searching for the radio, or why it is not connected;
// the counters are its hover title). There is no Reconnect: the radio is found again by itself (the daemon retries, probes a silent radio and follows an adapter that comes back as another port). An arrow in front opens what is behind it: the ports a search listens to, the problem when the line does not already say it, the fields of the radio (the
// default slot) and the Terminal (TncTerminal.vue). The Dummy radio is a muted pill and a line that says nothing goes on the air.
// The fold is closed unless the radio is not connected (`open`, which opens it when it turns true later and never closes it). Before the daemon has told the state of the radio the fields are there without the line.
import { computed } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import StatusFold from "@/components/StatusFold.vue";
import TncTerminal from "@/components/TncTerminal.vue";
import { t } from "@/i18n";
import { pillClass, pillText, searchedPorts, tncCounts, tncStatus } from "@/lib/tncstatus";
import type { TncState } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ tnc: TncState | null; now: number; open?: boolean }>(), { open: false });

const status = computed(() => (props.tnc === null ? "" : tncStatus(props.tnc, props.now)));
const ports = computed(() => (props.tnc === null ? null : searchedPorts(props.tnc)));
const problem = computed(() => (props.tnc !== null && props.tnc.problem !== "" && !status.value.includes(props.tnc.problem) ? props.tnc.problem : ""));
</script>

<template>
  <StatusFold v-if="tnc" class="radiostatus" :state="pillText(tnc)" :tone="pillClass(tnc)" :line="status" :hover="tncCounts(tnc)" :open="open">
    <DisclosureBox v-if="ports" :title="t('settings.tnc.ports')">
      <ul class="tncports mono">
        <li v-for="port in ports" :key="port">{{ port }}</li>
      </ul>
    </DisclosureBox>
    <p v-if="problem" class="problem" role="status">{{ problem }}</p>
    <slot></slot>
    <TncTerminal :tnc="tnc" />
  </StatusFold>
  <slot v-else></slot>
</template>
