<script setup lang="ts">
// The Email tab: a mail list, not a conversation, laid out like the Bulletins tab. At the top the one button Check email (`get`: the gateway sends again the mail it kept for this station; off while the radio of email is
// not connected, while there is none, or while a `get` is still being sent, the title says why), while several radios that can send are on the list of them, by name, which chooses the one radio email goes on (the
// setting `email/radio`, applied at once; it shows the radio in force, the daemon's `email_radio`; with one such radio email goes on it and there is no list), and an (i). The list (EmailList) fills the tab between them: the mail we sent with its state, and what the gateway EMAIL-2 sent us, the oldest first and scrolled to the newest, as Messages. At the bottom the box to
// write a mail in is always there (EmailCompose). The page sends it all as messages to EMAIL-2 (composables/useEmail.ts).
import { computed } from "vue";
import EmailCompose from "@/components/EmailCompose.vue";
import EmailList from "@/components/EmailList.vue";
import InfoTip from "@/components/InfoTip.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { radioBlockedReason } from "@/lib/compose";
import { checkingMail } from "@/lib/email";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ thread: readonly MessageRow[]; addresses: readonly string[]; freshAfter?: number }>(), {
  freshAfter: Number.MAX_SAFE_INTEGER,
});
const { heardDirect, settings } = useDaemonContext();
const emit = defineEmits<{
  send: [to: string, text: string];
  forget: [name: string];
  get: [];
  retry: [id: number];
  cancel: [id: number];
  delete: [id: number];
}>();

/** The setting that names the radio of email by its id. */
const KEY = "email/radio";
const radios = useRadios();
/** The radio email goes on, as the daemon says it; null while no radio that can send is on. */
const mail = computed(() => radios.email.value);
const named = computed(() => mail.value !== null && radios.named(mail.value.id));
/** Why email cannot go: there is no radio to send on, or the link of its radio is down; undefined while it can. */
const offline = computed(() => radioBlockedReason(mail.value, named.value));
/** The radios the list offers: every radio that can send, while several are on; none with one (email goes on it, and nothing is shown). */
const choices = computed(() => (radios.severalSenders.value ? radios.senders.value : []));
/** The radio the list shows: the one the setting names while it is one of the list (the one just picked too, while the daemon is asked), else the radio in force. */
const shown = computed(() => {
  const chosen = settings.draft[KEY] ?? "";
  if (choices.value.some((radio) => String(radio.id) === chosen)) return chosen;
  return mail.value === null ? "" : String(mail.value.id);
});

/** A radio picked in the list: stored at once. The list goes back to the radio in force when the daemon refuses it. */
function pick(event: Event): void {
  if (event.target instanceof HTMLSelectElement) settings.change({ [KEY]: event.target.value });
}
const checking = computed(() => checkingMail(props.thread));
const away = computed(() => offline.value ?? (checking.value ? t("email.checking") : undefined));
</script>

<template>
  <div class="mailpane">
    <div class="mail-bar">
      <button type="button" class="btn" :disabled="away !== undefined" :title="away" @click="emit('get')">{{ t("email.check") }}</button>
      <select v-if="choices.length > 0" class="input mail-radio" :value="shown" :aria-label="t('radio.choice')" @change="pick">
        <option v-for="radio in choices" :key="radio.id" :value="String(radio.id)">{{ radio.name }}</option>
      </select>
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
