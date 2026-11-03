<script setup lang="ts">
// The Help group, the last of the Settings tab but About: what to do when something does not work, in one line and one row with two buttons. The line names the address to e-mail the logs to, as the link that opens the person's mail program; **Download logs** asks the daemon
// for the support file and saves it (composables/useSupportLogs.ts); **Send logs** opens a dialog for a few words and then has the daemon send the file to the project, which answers with a reference; the (i) beside them says what the file holds. After
// either the group says the outcome in one quiet line: the file's name, the reference, or why not. The page sends nothing by itself: only Send in the dialog does, and the e-mail is the person's own.
import { computed, ref } from "vue";
import { t } from "@/i18n";
import SettingsGroup from "@/components/SettingsGroup.vue";
import ActionRow from "@/components/ActionRow.vue";
import RichMessage from "@/components/RichMessage.vue";
import SendLogsDialog from "@/components/SendLogsDialog.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useSupportLogs } from "@/composables/useSupportLogs";
import { SUPPORT_ADDRESS } from "@/lib/support";

const { call, connection, version, panel } = useDaemonContext();
const logs = useSupportLogs({ call, connection, daemonVersion: version, panelWidth: panel.width });
const label = computed(() => (logs.running.value ? t("settings.help.collecting") : t("settings.help.download")));
const sendLabel = computed(() => (logs.sending.value ? t("settings.help.sending") : t("settings.help.send")));
const busy = computed(() => logs.running.value || logs.sending.value);
const asking = ref(false);
const sendButton = ref<HTMLElement | null>(null);

function send(note: string): void {
  asking.value = false;
  void logs.send(note);
}
</script>

<template>
  <SettingsGroup id="help" class="help-logs" :title="t('settings.help.group')">
    <p>
      <RichMessage id="settings.help.text"
        ><template #address
          ><a :href="logs.mail.value">{{ SUPPORT_ADDRESS }}</a></template
        ></RichMessage
      >
    </p>
    <ActionRow id="set-help-logs" :label="t('settings.help.label')" :tip-label="t('settings.help.tip_label')" picture="logs">
      <button id="set-help-logs" class="btn" type="button" :disabled="busy" @click="logs.collect">{{ label }}</button>
      <button id="set-help-send" ref="sendButton" class="btn" type="button" :disabled="busy" @click="asking = true">{{ sendLabel }}</button>
      <template #tip
        ><span class="info-line">{{ t("settings.help.tip") }}</span
        ><span class="info-line">{{ t("settings.help.tip2") }}</span></template
      >
      <template #notes>
        <div class="help-result" role="status">
          <p v-if="logs.saved.value !== null" class="muted">{{ t("settings.help.saved", { file: logs.saved.value }) }}</p>
          <p v-else-if="logs.sentRef.value !== null" class="muted">
            <RichMessage id="settings.help.sent"
              ><template #ref
                ><span class="help-ref">{{ logs.sentRef.value }}</span></template
              ></RichMessage
            >
          </p>
          <p v-else-if="logs.problem.value" class="field-error">{{ logs.problem.value }}</p>
        </div>
      </template>
    </ActionRow>
    <Teleport v-if="asking" to="body">
      <SendLogsDialog :opener="sendButton" @send="send" @close="asking = false" />
    </Teleport>
  </SettingsGroup>
</template>
