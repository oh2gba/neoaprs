<script setup lang="ts">
// The one line at the top: the title, our call (amber "no call set", a button that opens the first-run guide, while none is set: nothing is transmitted then; with the number of messages not seen, a button that opens them), one dot and the words for whether the radio works, a button that opens the Settings tab, where the radio is (green "radio ok": the page's socket is open and
// the TNC is connected; amber "radio: searching", "radio: waiting", "radio: entering KISS" or "radio: stopped": the socket is up and the TNC is not, its problem the title; amber "radio: silent": the line is
// open and the radio does not answer, the title says since when; red "daemon offline": the socket is down). What the daemon costs the machine (the CPU share, the memory, the uptime) is not shown, only in the title of the radio state. The port and what the TNC last heard are at the top of the TNC group of the Settings tab. When the update check has found a newer
// version it is shown after the version number, a button that opens the panel with the steps to it (UpdatePanel), the project's note as the title; on a phone, where the version number is left out, the button stays ("Update") so that the update is not missed.
import { computed } from "vue";
import type { Connection } from "@/lib/hub";
import { processText, silentText } from "@/lib/format";
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
const emit = defineEmits<{ messages: []; setup: []; update: []; radio: [] }>();

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
/** What the daemon costs the machine, for the title of the radio state: "0.3 % · 42 MB · up 3 h". */
const cost = computed(() => (props.status ? processText(props.status.cpu_percent, props.status.rss_mb, props.status.uptime_sec) : null));
const hover = computed(() => [link.value.title, cost.value === null ? null : `NeoAPRS uses ${cost.value}`].filter((text) => text).join("\n") || undefined);
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
    <span class="statuswrap" role="status">
      <button type="button" class="status" :class="`link-${link.level}`" :title="hover" @click="emit('radio')">
        <span class="dot" aria-hidden="true"></span>
        {{ link.text }}
      </button>
    </span>
    <span v-if="version" class="muted version">v{{ version }}</span>
    <button v-if="status?.update" type="button" class="update" :title="status.update.message || `Update to ${status.update.version}`" @click="emit('update')">
      Update<span class="update-to"> to {{ status.update.version }}</span>
    </button>
  </header>
</template>
