<script setup lang="ts">
// The one small line under the panel (not under the map; on a phone under the open tab, not on the map's turn): at the right the state of the radio, only when it is NOT ok, in the warning colour (red for "Daemon offline"), a button that opens the Settings tab, where the radio is:
// "Radio: searching…", "Radio: entering KISS…", "Radio: not connected" (the TNC waits between two tries, or is stopped, its problem the title), "Radio: silent" (the line is open and the radio does not answer, the title says since when), "Connecting…" (the page's socket is being opened), "Daemon offline" (it is down).
// When the radio is fine the line says nothing of it. The line has the same height all the time (ui/src/styles/base.css), so nothing moves when the message comes or goes. The version is in Settings → New version, a newer one is the mark Update at the top.
import { computed } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import { silentText } from "@/lib/format";

const { connection: link, tnc, now } = useDaemonContext();
const emit = defineEmits<{ radio: [] }>();

type Trouble = { level: "warn" | "bad"; text: string; title?: string };
/** What is wrong with the radio link, or null when nothing is: the radio is connected. */
const trouble = computed<Trouble | null>(() => {
  const connection = link.value;
  const radio = tnc.value;
  if (connection === "closed") return { level: "bad", text: t("footer.offline") };
  if (connection === "connecting") return { level: "warn", text: t("footer.connecting") };
  if (radio === null) return { level: "warn", text: t("footer.radio.waiting"), title: t("footer.radio.waiting_title") };
  if (radio.state === "connected") return null;
  if (radio.state === "silent") return { level: "warn", text: t("footer.radio.silent"), title: silentText(radio.silent_since, now.value) };
  const why = radio.problem || radio.describe || radio.state;
  if (radio.state === "connecting")
    return { level: "warn", text: t(radio.describe.includes("entering KISS") ? "footer.radio.entering_kiss" : "footer.radio.searching"), title: why };
  return { level: "warn", text: t("footer.radio.not_connected"), title: why };
});
</script>

<template>
  <footer class="panelfoot">
    <span class="footradio" role="status">
      <button
        v-if="trouble"
        type="button"
        class="status"
        :class="`link-${trouble.level}`"
        :title="trouble.title ?? t('footer.radio.open_settings')"
        @click="emit('radio')"
      >
        {{ trouble.text }}
      </button>
    </span>
  </footer>
</template>
