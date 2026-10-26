<script setup lang="ts">
// The Help group, the last of the Settings tab: what to do when something does not work. One plain button, **Download logs**, asks the daemon for the support file and saves it (composables/useSupportLogs.ts); under it one quiet line says what the file holds
// and where the manual lists it; after a download the group says the file's name and offers the e-mail to write, with the form of what to tell in it, or says why there is no file. The page sends nothing by itself: the e-mail is the person's own.
import { computed } from "vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useSupportLogs } from "@/composables/useSupportLogs";
import { SUPPORT_ADDRESS, SUPPORT_MANUAL } from "@/lib/support";

const { call, connection, version, panel } = useDaemonContext();
const logs = useSupportLogs({ call, connection, daemonVersion: version, panelWidth: panel.width });
const address = { address: SUPPORT_ADDRESS };
const label = computed(() => (logs.running.value ? t("settings.help.collecting") : t("settings.help.download")));
</script>

<template>
  <fieldset class="help-logs">
    <legend>{{ t("settings.help.group") }}</legend>
    <p>{{ t("settings.help.text", address) }}</p>
    <button class="btn" type="button" :disabled="logs.running.value" @click="logs.collect">{{ label }}</button>
    <p class="muted">{{ t("settings.help.contents") }}</p>
    <p>
      <a class="help-link" :href="SUPPORT_MANUAL" target="_blank" rel="noopener noreferrer">{{ t("settings.help.contents_link") }}</a>
    </p>
    <div class="help-result" role="status">
      <template v-if="logs.saved.value !== null">
        <p class="muted">{{ t("settings.help.saved", { file: logs.saved.value }) }}</p>
        <p>
          <a class="help-link" :href="logs.mail.value">{{ t("settings.help.write", address) }}</a>
        </p>
      </template>
      <p v-else-if="logs.problem.value" class="field-error">{{ logs.problem.value }}</p>
    </div>
  </fieldset>
</template>
