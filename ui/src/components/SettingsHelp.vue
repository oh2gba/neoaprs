<script setup lang="ts">
// The Help group, the last of the Settings tab but About: what to do when something does not work, in one line and one row with a button. The line names the address to send the logs to, as the link that opens the person's mail program; **Download logs** asks the daemon for the support file
// and saves it (composables/useSupportLogs.ts); the (i) beside it says what the file holds. After a download the group says the file's name, or why there is no file. The page sends nothing by itself: the e-mail is the person's own.
import { computed } from "vue";
import { t } from "@/i18n";
import ActionRow from "@/components/ActionRow.vue";
import RichMessage from "@/components/RichMessage.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useSupportLogs } from "@/composables/useSupportLogs";
import { SUPPORT_ADDRESS } from "@/lib/support";

const { call, connection, version, panel } = useDaemonContext();
const logs = useSupportLogs({ call, connection, daemonVersion: version, panelWidth: panel.width });
const label = computed(() => (logs.running.value ? t("settings.help.collecting") : t("settings.help.download")));
</script>

<template>
  <fieldset class="help-logs">
    <legend>{{ t("settings.help.group") }}</legend>
    <p>
      <RichMessage id="settings.help.text"
        ><template #address
          ><a :href="logs.mail.value">{{ SUPPORT_ADDRESS }}</a></template
        ></RichMessage
      >
    </p>
    <ActionRow id="set-help-logs" :label="t('settings.help.label')" :tip-label="t('settings.help.tip_label')" picture="logs">
      <button id="set-help-logs" class="btn" type="button" :disabled="logs.running.value" @click="logs.collect">{{ label }}</button>
      <template #tip
        ><span class="info-line">{{ t("settings.help.tip") }}</span></template
      >
      <template #notes>
        <div class="help-result" role="status">
          <p v-if="logs.saved.value !== null" class="muted">{{ t("settings.help.saved", { file: logs.saved.value }) }}</p>
          <p v-else-if="logs.problem.value" class="field-error">{{ logs.problem.value }}</p>
        </div>
      </template>
    </ActionRow>
  </fieldset>
</template>
