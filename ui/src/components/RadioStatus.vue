<script setup lang="ts">
// The TNC group of the Settings tab: one line in view, the state of the radio link as a pill and plain words (lib/tncstatus.ts: what it is connected to and when a packet last came, that it is searching for the radio, or why it is not connected;
// the counters are its hover title) with a small Reconnect at its end, and an arrow in front that opens what is behind it: the ports a search listens to, the problem when the line does not already say it, the fields of the radio (the
// default slot) and the Terminal (TncTerminal.vue). The Dummy radio is a muted pill and a line that says nothing goes on the air.
// The fold is closed unless the radio is not connected (`open`, which opens it when it turns true later and never closes it). Before the daemon has told the state of the radio the fields are there without the line.
import { computed } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import TncTerminal from "@/components/TncTerminal.vue";
import { t } from "@/i18n";
import { pillClass, pillText, searchedPorts, tncCounts, tncStatus } from "@/lib/tncstatus";
import type { TncState } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ tnc: TncState | null; now: number; digipeater?: boolean; open?: boolean }>(), { digipeater: false, open: false });
const emit = defineEmits<{ reconnect: [] }>();

const status = computed(() => (props.tnc === null ? "" : tncStatus(props.tnc, props.now, props.digipeater)));
const ports = computed(() => (props.tnc === null ? null : searchedPorts(props.tnc)));
const problem = computed(() => (props.tnc !== null && props.tnc.problem !== "" && !status.value.includes(props.tnc.problem) ? props.tnc.problem : ""));
</script>

<template>
  <DisclosureBox v-if="tnc" class="radiostatus" :title="status" :open="open" summary-class="radiohead">
    <template #summary>
      <span class="statetext" :class="pillClass(tnc)">{{ pillText(tnc) }}</span>
      <span class="tncstatus" role="status" :title="tncCounts(tnc)">{{ status }}</span>
      <button class="btn" type="button" @click.stop.prevent="emit('reconnect')">{{ t("settings.tnc.reconnect") }}</button>
    </template>
    <DisclosureBox v-if="ports" :title="t('settings.tnc.ports')">
      <ul class="tncports mono">
        <li v-for="port in ports" :key="port">{{ port }}</li>
      </ul>
    </DisclosureBox>
    <p v-if="problem" class="problem" role="status">{{ problem }}</p>
    <slot></slot>
    <TncTerminal :tnc="tnc" />
  </DisclosureBox>
  <slot v-else></slot>
</template>
