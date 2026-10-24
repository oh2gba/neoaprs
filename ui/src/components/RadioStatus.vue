<script setup lang="ts">
// The TNC group of the Settings tab: one line in view, the state of the radio link as a pill and plain words (lib/tncstatus.ts: what it is connected to and when a packet last came, that it is searching for the radio, or why it is not connected;
// the counters are its hover title) with a small Reconnect at its end, and an arrow in front that opens what is behind it: the ports a search listens to, the problem when the line does not already say it, the fields of the radio (the
// default slot) and "Terminal", which is closed until it is wanted: the latest lines of what the TNC saw and did, newest last, in the viewer's time, following the end unless it was scrolled up.
// The fold is closed unless the radio is not connected (`open`, which opens it when it turns true later and never closes it). Before the daemon has told the state of the radio the fields are there without the line.
import { computed, nextTick, ref, watch } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import { t } from "@/i18n";
import { lineText, searchedPorts, stateText, tncCounts, tncStatus } from "@/lib/tncstatus";
import type { TncState } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ tnc: TncState | null; now: number; digipeater?: boolean; open?: boolean }>(), { digipeater: false, open: false });
const emit = defineEmits<{ reconnect: [] }>();

const log = ref<HTMLElement | null>(null);
const FOLLOW_SLACK_PX = 24;
const status = computed(() => (props.tnc === null ? "" : tncStatus(props.tnc, props.now, props.digipeater)));
const ports = computed(() => (props.tnc === null ? null : searchedPorts(props.tnc)));
const problem = computed(() => (props.tnc !== null && props.tnc.problem !== "" && !status.value.includes(props.tnc.problem) ? props.tnc.problem : ""));
const lines = computed(() => (props.tnc?.lines ?? []).map(lineText));

watch(
  () => props.tnc?.lines,
  async () => {
    const box = log.value;
    if (!box) return;
    const atEnd = box.scrollHeight - box.scrollTop - box.clientHeight <= FOLLOW_SLACK_PX;
    await nextTick();
    if (atEnd) box.scrollTop = box.scrollHeight;
  },
);

/** The end of the lines is in view when the terminal is opened. */
async function opened(): Promise<void> {
  await nextTick();
  if (log.value) log.value.scrollTop = log.value.scrollHeight;
}
</script>

<template>
  <DisclosureBox v-if="tnc" class="radiostatus" :title="status" :open="open" summary-class="radiohead">
    <template #summary>
      <span class="statepill" :class="`tnc-${tnc.state}`">{{ stateText(tnc.state) }}</span>
      <span class="tncstatus" role="status" :title="tncCounts(tnc)">{{ status }}</span>
      <button class="btn small" type="button" @click.stop.prevent="emit('reconnect')">{{ t("settings.tnc.reconnect") }}</button>
    </template>
    <DisclosureBox v-if="ports" :title="t('settings.tnc.ports')">
      <ul class="tncports mono">
        <li v-for="port in ports" :key="port">{{ port }}</li>
      </ul>
    </DisclosureBox>
    <p v-if="problem" class="problem" role="status">{{ problem }}</p>
    <slot></slot>
    <DisclosureBox :title="t('settings.tnc.terminal')" @toggle="opened">
      <pre ref="log" class="tnclines" :aria-label="t('settings.tnc.terminal_label')">{{ lines.join("\n") }}</pre>
    </DisclosureBox>
  </DisclosureBox>
  <slot v-else></slot>
</template>
