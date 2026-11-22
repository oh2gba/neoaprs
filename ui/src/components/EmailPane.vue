<script setup lang="ts">
// The Email tab: a mail list laid out like the Bulletins tab. Check email (`get`) asks the
// gateway to resend the mail it kept. While several sending radios are on, a Send on list
// chooses the radio email goes on (setting `email/radio`, applied at once). The list (EmailList)
// fills the tab; the compose box (EmailCompose) is always at the bottom. Everything goes as
// messages to EMAIL-2 (composables/useEmail.ts).
import { computed, useId } from "vue";
import EmailCompose from "@/components/EmailCompose.vue";
import EmailList from "@/components/EmailList.vue";
import InfoTip from "@/components/InfoTip.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { radioBlockedReason } from "@/lib/compose";
import { checkingMail } from "@/lib/email";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{ thread: readonly MessageRow[]; addresses: readonly string[]; freshAfter?: number }>(),
  {
    freshAfter: Number.MAX_SAFE_INTEGER,
  },
);
const { heardDirect, settings } = useDaemonContext();
const emit = defineEmits<{
  send: [to: string, text: string];
  forget: [name: string];
  get: [];
  retry: [id: number];
  cancel: [id: number];
  delete: [id: number];
}>();

/** The setting that holds the email radio's id. */
const KEY = "email/radio";
const radios = useRadios();
/** The radio email goes on, as the daemon reports it; null while no sending radio is on. */
const mail = computed(() => radios.email.value);
const named = computed(() => mail.value !== null && radios.named(mail.value.id));
/** Why email cannot go: no radio to send on, or its link is down; undefined when it can. */
const offline = computed(() => radioBlockedReason(mail.value, named.value));
/** The radios offered in the list: every sending radio while several are on; none with one. */
const choices = computed(() => (radios.severalSenders.value ? radios.senders.value : []));
/** The list's id, which the label Send on points at. */
const listId = useId();
/** The radio the list shows: the one the setting names (or the one just picked), else the one in
 * force. */
const shown = computed(() => {
  const chosen = settings.draft[KEY] ?? "";
  if (choices.value.some((radio) => String(radio.id) === chosen)) return chosen;
  return mail.value === null ? "" : String(mail.value.id);
});

/** A radio picked in the list is stored at once; it reverts when the daemon refuses it. */
function pick(event: Event): void {
  if (event.target instanceof HTMLSelectElement) settings.change({ [KEY]: event.target.value });
}
const checking = computed(() => checkingMail(props.thread));
const away = computed(() => offline.value ?? (checking.value ? t("email.checking") : undefined));
</script>

<template>
  <div class="mailpane">
    <div class="mail-bar">
      <button type="button" class="btn" :disabled="away !== undefined" :title="away" @click="emit('get')">
        {{ t("email.check") }}
      </button>
      <div v-if="choices.length > 0" class="pathbox mail-radio">
        <label :for="listId" class="path-label">{{ t("radio.send_on") }}</label>
        <select :id="listId" class="input" :value="shown" @change="pick">
          <option v-for="radio in choices" :key="radio.id" :value="String(radio.id)">{{ radio.name }}</option>
        </select>
      </div>
      <span class="grow" />
      <InfoTip :label="t('email.about')">
        <span class="info-line">{{ t("email.about_gateway", { unconfirmed: t("email.state.unconfirmed") }) }}</span>
        <span class="info-line">{{ t("email.about_check", { check: t("email.check") }) }}</span>
      </InfoTip>
    </div>
    <EmailList
      :thread="thread"
      :fresh-after="freshAfter"
      :heard-direct="heardDirect"
      :offline="offline"
      @retry="emit('retry', $event)"
      @cancel="emit('cancel', $event)"
      @delete="emit('delete', $event)"
    />
    <EmailCompose
      :connected="offline === undefined"
      :offline="offline"
      :addresses="addresses"
      @send="(to, text) => emit('send', to, text)"
      @forget="emit('forget', $event)"
    />
  </div>
</template>
