<script setup lang="ts">
// The one line at the top: the title, our call (amber "no call set", a button that opens the first-run guide, while none is set: nothing is transmitted then; with the number of messages not seen, a button that opens them), one dot and the words for whether the radio works (green "radio ok": the page's socket is open and
// the TNC is connected; amber "radio: searching", "radio: waiting", "radio: entering KISS" or "radio: stopped": the socket is up and the TNC is not, its problem the title; amber "radio: silent": the line is
// open and the radio does not answer, the title says since when; red "daemon offline": the socket is down)
// and, small and muted beside them, what the daemon costs the machine (the full figures with the uptime are the title). The port, the speed and the packet count are on the TNC tab. When the daily update check has found a newer
// version it is shown after the version number, a link to the project's page with the project's note as the title.
import { computed } from "vue";
import type { Connection } from "@/lib/hub";
import { processText, processTextShort, silentText } from "@/lib/format";
import { unreadText } from "@/lib/unread";
import type { StatusMessage, TncState } from "@/protocol/protocol";

const props = defineProps<{
  /** Our call from the settings; empty while none is set, null while the daemon has not said. */
  call: string | null;
  connection: Connection;
  tnc: TncState | null;
  version: string;
  unread: number;
  now: number;
  status?: StatusMessage | null;
}>();
const emit = defineEmits<{ messages: []; setup: [] }>();

type Link = { level: "ok" | "warn" | "bad"; text: string; title?: string };
/** The TNC's state in a word: it is searching for the port until the line is open, then entering KISS. */
function radioWord(tnc: TncState | null): string {
  if (tnc === null) return "waiting";
  if (tnc.state === "connecting") return tnc.describe.includes("entering KISS") ? "entering KISS" : "searching";
  return tnc.state;
}
const link = computed<Link>(() => {
  if (props.connection === "closed") return { level: "bad", text: "daemon offline" };
  if (props.connection === "connecting") return { level: "warn", text: "connecting..." };
  if (props.tnc?.state === "connected") return { level: "ok", text: "radio ok" };
  if (props.tnc?.state === "silent") return { level: "warn", text: "radio: silent", title: silentText(props.tnc.silent_since, props.now) };
  return {
    level: "warn",
    text: `radio: ${radioWord(props.tnc)}`,
    title: props.tnc === null ? "no word from the TNC yet" : props.tnc.problem || props.tnc.describe || props.tnc.state,
  };
});
const process = computed(() =>
  props.status
    ? {
        short: processTextShort(props.status.cpu_percent, props.status.rss_mb),
        full: processText(props.status.cpu_percent, props.status.rss_mb, props.status.uptime_sec),
      }
    : null,
);
</script>

<template>
  <header class="appheader">
    <h1>NeoAPRS</h1>
    <span v-if="call" class="mono call">{{ call }}</span>
    <button v-else-if="call === ''" type="button" class="nocall" title="Nothing is transmitted until a call is set: open the setup" @click="emit('setup')">
      no call set
    </button>
    <button v-if="unread > 0" type="button" class="badge headmail" :title="`${unreadText(unread)}: open the messages`" @click="emit('messages')">
      <span aria-hidden="true">&#9993;</span> {{ unread }}<span class="sr-only"> {{ unreadText(unread) }}</span>
    </button>
    <span class="status" :class="`link-${link.level}`" role="status" :title="link.title">
      <span class="dot" aria-hidden="true"></span>
      {{ link.text }}
    </span>
    <span v-if="process" class="muted process" :title="process.full">{{ process.short }}</span>
    <span v-if="version" class="muted version">v{{ version }}</span>
    <a
      v-if="status?.update?.url"
      class="update"
      :href="status.update.url"
      :title="status.update.message || undefined"
      target="_blank"
      rel="noopener noreferrer"
      >{{ status.update.version }}</a
    >
    <span v-else-if="status?.update" class="update" :title="status.update.message || undefined">{{ status.update.version }}</span>
  </header>
</template>
