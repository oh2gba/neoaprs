<script setup lang="ts">
// The radio link at the top of the TNC group of the Settings tab: the state as a pill, one plain line (lib/tncstatus.ts: what it is connected to and when a packet last came, that it is searching for the radio with the ports it listens to behind "Ports", or why it is not connected;
// the counters are its hover title), the problem when the line does not already say it, and Reconnect. "Terminal" is closed until it is wanted: the latest lines of what the TNC saw and did, newest last, in the viewer's time, following the end unless it was scrolled up.
import { computed, nextTick, ref, watch } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import { localLine, searchedPorts, tncCounts, tncStatus } from "@/lib/tncstatus";
import type { TncState } from "@/protocol/protocol";

const props = defineProps<{ tnc: TncState | null; now: number }>();
const emit = defineEmits<{ reconnect: [] }>();

const log = ref<HTMLElement | null>(null);
const FOLLOW_SLACK_PX = 24;
const status = computed(() => (props.tnc === null ? "" : tncStatus(props.tnc, props.now)));
const ports = computed(() => (props.tnc === null ? null : searchedPorts(props.tnc)));
const problem = computed(() => (props.tnc !== null && props.tnc.problem !== "" && !status.value.includes(props.tnc.problem) ? props.tnc.problem : ""));
const lines = computed(() => (props.tnc?.lines ?? []).map((l) => localLine(l, props.now)));

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
  <div v-if="tnc" class="radiostatus">
    <div class="radiostatus-head">
      <span class="statepill" :class="`tnc-${tnc.state}`">{{ tnc.state }}</span>
      <button class="btn" type="button" @click="emit('reconnect')">Reconnect</button>
    </div>
    <p class="tncstatus" role="status" :title="tncCounts(tnc)">{{ status }}</p>
    <DisclosureBox v-if="ports" title="Ports">
      <ul class="tncports mono">
        <li v-for="port in ports" :key="port">{{ port }}</li>
      </ul>
    </DisclosureBox>
    <p v-if="problem" class="problem" role="status">{{ problem }}</p>
    <DisclosureBox title="Terminal" @toggle="opened">
      <pre ref="log" class="tnclines" aria-label="What the TNC saw and did">{{ lines.join("\n") }}</pre>
    </DisclosureBox>
  </div>
</template>
