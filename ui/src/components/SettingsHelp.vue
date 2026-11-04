<script setup lang="ts">
// The Help group, the last of the Settings tab but About: the one way to reach the project, **Send feedback / logs**, as the group's primary button with a line above it. It opens a dialog for a few words
// with the logs file shown attached, and then has the daemon send both to the project, which answers with a reference (composables/useSupportLogs.ts); the (i) beside it says what goes. The group says the
// outcome in one quiet line: the reference, or why not. Saving the logs as a file is About's last line (SettingsAbout); nothing is sent before Send in the dialog.
import { computed, ref } from "vue";
import { t } from "@/i18n";
import SettingsGroup from "@/components/SettingsGroup.vue";
import ActionRow from "@/components/ActionRow.vue";
import RichMessage from "@/components/RichMessage.vue";
import SendLogsDialog from "@/components/SendLogsDialog.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useSupportLogs } from "@/composables/useSupportLogs";

const { call, connection, version, panel } = useDaemonContext();
const logs = useSupportLogs({ call, connection, daemonVersion: version, panelWidth: panel.width });
const sendLabel = computed(() => (logs.sending.value ? t("settings.help.sending") : t("settings.help.send")));
const asking = ref(false);
const sendButton = ref<HTMLElement | null>(null);

function send(note: string): void {
  asking.value = false;
  void logs.send(note);
}
</script>

<template>
  <SettingsGroup id="help" class="help-logs" :title="t('settings.help.group')">
    <p>{{ t("settings.help.text") }}</p>
    <ActionRow id="set-help-send" :label="t('settings.help.label')" :tip-label="t('settings.help.tip_label')" picture="logs">
      <button id="set-help-send" ref="sendButton" class="btn primary" type="button" :disabled="logs.sending.value || logs.running.value" @click="asking = true">
        {{ sendLabel }}
      </button>
      <template #tip
        ><span class="info-line">{{ t("settings.help.tip") }}</span
        ><span class="info-line">{{ t("settings.help.tip2") }}</span></template
      >
      <template #notes>
        <div class="help-result" role="status">
          <p v-if="logs.sentRef.value !== null" class="muted">
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
      <SendLogsDialog :opener="sendButton" :call="call" @send="send" @close="asking = false" />
    </Teleport>
  </SettingsGroup>
</template>
