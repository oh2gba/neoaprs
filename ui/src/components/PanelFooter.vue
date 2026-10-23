<script setup lang="ts">
// The one small line under the panel (not under the map; on a phone under the open tab, not on the map's turn): at the left the version of NeoAPRS and, when the update check has found a newer one, "Update to 0.6.1", a button that opens the panel with the steps to it
// (UpdatePanel), the project's note as its title; at the right the state of the radio, only when it is NOT ok, in the warning colour (red for "Daemon offline"), a button that opens the Settings tab, where the radio is: "Radio: searching…", "Radio: entering KISS…",
// "Radio: not connected" (the TNC waits between two tries, or is stopped, its problem the title), "Radio: silent" (the line is open and the radio does not answer, the title says since when), "Connecting…" (the page's socket is being opened), "Daemon offline" (it is down).
// When the radio is fine the line says nothing of it. The line has the same height all the time (style.css), so nothing moves when the message comes or goes. What the daemon costs the machine (the CPU share, the memory, the uptime) is the title of the version.
import { computed } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { processText, silentText } from "@/lib/format";

const { connection: link, tnc, version, now, status } = useDaemonContext();
const emit = defineEmits<{ update: []; radio: [] }>();

type Trouble = { level: "warn" | "bad"; text: string; title?: string };
/** What is wrong with the radio link, or null when nothing is: the radio is connected. */
const trouble = computed<Trouble | null>(() => {
  const connection = link.value;
  const radio = tnc.value;
  if (connection === "closed") return { level: "bad", text: "Daemon offline" };
  if (connection === "connecting") return { level: "warn", text: "Connecting…" };
  if (radio === null) return { level: "warn", text: "Radio: waiting…", title: "no word from the TNC yet" };
  if (radio.state === "connected") return null;
  if (radio.state === "silent") return { level: "warn", text: "Radio: silent", title: silentText(radio.silent_since, now.value) };
  const why = radio.problem || radio.describe || radio.state;
  if (radio.state === "connecting")
    return { level: "warn", text: radio.describe.includes("entering KISS") ? "Radio: entering KISS…" : "Radio: searching…", title: why };
  return { level: "warn", text: "Radio: not connected", title: why };
});
/** What the daemon costs the machine, for the title of the version: "0.3 % · 42 MB · up 3 h". */
const cost = computed(() => (status.value ? processText(status.value.cpu_percent, status.value.rss_mb, status.value.uptime_sec) : null));
</script>

<template>
  <footer class="panelfoot">
    <span v-if="version" class="muted version" :title="cost === null ? undefined : `NeoAPRS uses ${cost}`">NeoAPRS {{ version }}</span>
    <button v-if="status?.update" type="button" class="update" :title="status.update.message || `Update to ${status.update.version}`" @click="emit('update')">
      Update to {{ status.update.version }}
    </button>
    <span class="footradio" role="status">
      <button
        v-if="trouble"
        type="button"
        class="status"
        :class="`link-${trouble.level}`"
        :title="trouble.title ?? 'Open the radio settings'"
        @click="emit('radio')"
      >
        {{ trouble.text }}
      </button>
    </span>
  </footer>
</template>
