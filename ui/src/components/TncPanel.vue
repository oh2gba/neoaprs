<script setup lang="ts">
// The radio link: the state of the TNC and why when it is not connected, the port and speed, what it has counted, and the latest lines of what it saw and did (newest last, the list follows
// the end unless it was scrolled up; a silent radio is told since when instead of the daemon's line, which has the time in UTC). "Reconnect" opens the line again.
import { nextTick, ref, watch } from "vue";
import { bytesText, ageText, silentText, NONE } from "@/lib/format";
import type { TncState } from "@/protocol/protocol";

const props = defineProps<{ tnc: TncState | null; now: number }>();
const emit = defineEmits<{ reconnect: [] }>();

const log = ref<HTMLElement | null>(null);
const FOLLOW_SLACK_PX = 24;

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
      <span class="grow muted">{{ tnc.state === "silent" ? silentText(tnc.silent_since, now) : tnc.describe }}</span>
      <button class="btn" type="button" @click="emit('reconnect')">Reconnect</button>
    </div>
    <p v-if="tnc.problem" class="problem" role="status">{{ tnc.problem }}</p>
    <dl class="card-fields">
      <dt>Port</dt>
      <dd class="mono">{{ tnc.path || NONE }}</dd>
      <dt>Speed</dt>
      <dd>{{ tnc.baud }} baud</dd>
      <dt>Last error</dt>
      <dd>{{ tnc.last_error || NONE }}</dd>
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
    <pre ref="log" class="tnclines" aria-label="What the TNC saw and did">{{ tnc.lines.join("\n") }}</pre>
  </div>
  <p v-else class="empty">No word from the daemon yet.</p>
</template>
