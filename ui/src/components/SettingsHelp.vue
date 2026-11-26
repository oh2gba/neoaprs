<script setup lang="ts">
// The Help group: Send feedback / logs as the group's primary button. It opens SendLogsDialog with
// the logs file attached; Send has the daemon send the words and the file (or the words alone) to
// the project, which answers with a reference (useSupportLogs). The outcome shows in one quiet
// line. The group keeps what the dialog holds until a send worked: the words, the address for a
// reply and whether the file is on. The downloaded file is kept from the download to the Send of that opening, and for a retry
// after a failed send; a dialog closed without sending forgets it, so a later Send uses fresh logs.
import { computed, ref, watch } from "vue";
import { t } from "@/i18n";
import SettingsGroup from "@/components/SettingsGroup.vue";
import ActionRow from "@/components/ActionRow.vue";
import RichMessage from "@/components/RichMessage.vue";
import SendLogsDialog from "@/components/SendLogsDialog.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useSupportLogs } from "@/composables/useSupportLogs";

const { call, connection, version, panel } = useDaemonContext();
const given = { call, connection, daemonVersion: version, panelWidth: panel.width };
const logs = useSupportLogs(given);
/**
 * The dialog file's download and what the dialog says of it, held here so that it is the same one
 * at the next opening while it runs and after a failed send.
 */
const download = useSupportLogs(given);
const sendLabel = computed(() => (logs.sending.value ? t("settings.help.sending") : t("settings.help.send")));
const asking = ref(false);
/** The words and the address for a reply of the dialog, kept until sent: a failed send does not clear them. */
const draft = ref("");
const email = ref("");
/** Whether the file goes with the words: off when the person removed it, kept with the words. */
const attached = ref(true);
/**
 * The file the daemon made for the latest download from the open dialog, by its full name: Send
 * names it. A download that ends while the dialog is closed is saved and not named.
 */
const made = ref<string | null>(null);
watch(
  download.saved,
  (saved) => {
    if (asking.value) made.value = saved ?? made.value;
  },
  { flush: "sync" },
);
const sendButton = ref<HTMLElement | null>(null);

/**
 * Open the dialog. It says Saved only for the file Send will name; earlier failures and downloads
 * ending while closed are not repeated.
 */
function ask(): void {
  if (!download.running.value && (made.value === null || download.problem.value !== "")) download.clear();
  asking.value = true;
}

/**
 * Close the dialog without sending: the words and the attach state stay; the downloaded file does
 * not.
 */
function close(): void {
  asking.value = false;
  made.value = null;
}

async function send(note: string, withFile: boolean, address: string): Promise<void> {
  asking.value = false;
  await logs.send(note, withFile ? (made.value ?? true) : false, address);
  if (logs.sentRef.value === null) return;
  draft.value = "";
  email.value = "";
  attached.value = true;
  made.value = null;
  download.clear();
}
</script>

<template>
  <SettingsGroup id="help" class="help-logs" :title="t('settings.help.group')">
    <p>{{ t("settings.help.text") }}</p>
    <ActionRow
      id="set-help-send"
      :label="t('settings.help.label')"
      :tip-label="t('settings.help.tip_label')"
      picture="logs"
    >
      <button
        id="set-help-send"
        ref="sendButton"
        class="btn primary"
        type="button"
        :disabled="logs.sending.value || logs.running.value"
        @click="ask"
      >
        {{ sendLabel }}
      </button>
      <template #tip
        ><span class="info-line">{{ t("settings.help.tip") }}</span></template
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
      <SendLogsDialog
        :draft="draft"
        :email="email"
        :attached="attached"
        :download="download"
        :call="call"
        :opener="sendButton"
        @draft="draft = $event"
        @email="email = $event"
        @attached="attached = $event"
        @send="send"
        @close="close"
      />
    </Teleport>
  </SettingsGroup>
</template>
