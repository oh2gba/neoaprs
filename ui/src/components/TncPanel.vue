<script setup lang="ts">
// The radio link: the state of the TNC as a pill and one plain line (lib/tncstatus.ts: what it is connected to and how many packets it has heard, or that it is searching for the radio, with the ports it listens to behind a click), why it is not connected when it is not,
// the latest lines of what it saw and did (newest last, times in the viewer's time; the list follows the end unless it was scrolled up), and, behind "Details", the port, the speed, the last error (only when there was one) and what it has counted. "Reconnect" opens the line again.
import { computed, nextTick, ref, watch } from "vue";
import Disclosure from "@/components/Disclosure.vue";
import { ageText, bytesText, NONE } from "@/lib/format";
import { localLine, searchedPorts, tncStatus } from "@/lib/tncstatus";
import type { TncState } from "@/protocol/protocol";

const props = defineProps<{ tnc: TncState | null; now: number }>();
const emit = defineEmits<{ reconnect: [] }>();

const log = ref<HTMLElement | null>(null);
const FOLLOW_SLACK_PX = 24;
const ports = computed(() => (props.tnc === null ? null : searchedPorts(props.tnc)));
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
</script>

<template>
  <div v-if="tnc" class="tncpane">
    <div class="toolbar">
      <span class="statepill" :class="`tnc-${tnc.state}`">{{ tnc.state }}</span>
      <span class="grow" />
      <button class="btn" type="button" @click="emit('reconnect')">Reconnect</button>
    </div>
    <p class="tncstatus" role="status">{{ tncStatus(tnc, now) }}</p>
    <Disclosure v-if="ports" title="Ports">
      <ul class="tncports mono">
        <li v-for="port in ports" :key="port">{{ port }}</li>
      </ul>
    </Disclosure>
    <p v-if="tnc.problem" class="problem" role="status">{{ tnc.problem }}</p>
    <Disclosure title="Details">
      <dl class="card-fields">
        <dt>Port</dt>
        <dd class="mono">{{ tnc.path || NONE }}</dd>
        <dt>Speed</dt>
        <dd>{{ tnc.baud }} baud</dd>
        <template v-if="tnc.last_error">
          <dt>Last error</dt>
          <dd>{{ tnc.last_error }}</dd>
        </template>
        <dt>Opened</dt>
        <dd>{{ tnc.stats.opens }} times</dd>
        <dt>Bytes</dt>
        <dd>{{ bytesText(tnc.stats.bytes_in) }} in, {{ bytesText(tnc.stats.bytes_out) }} out</dd>
        <dt>Frames</dt>
        <dd>{{ tnc.stats.frames_in }} received, {{ tnc.stats.rejected }} rejected</dd>
        <dt>Packets</dt>
        <dd>{{ tnc.stats.packets }}, the latest {{ tnc.stats.last_packet === null ? "none yet" : `${ageText(tnc.stats.last_packet, now)} ago` }}</dd>
        <dt>Keep-alive</dt>
        <dd>{{ tnc.stats.keepalive_checks }} checks, {{ tnc.stats.watchdog_probes }} probes, {{ tnc.stats.port_reopens }} reopens</dd>
      </dl>
    </Disclosure>
    <pre ref="log" class="tnclines" aria-label="What the TNC saw and did">{{ lines.join("\n") }}</pre>
  </div>
  <p v-else class="empty">No word from the daemon yet.</p>
</template>
