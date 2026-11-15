<script setup lang="ts">
// The Email tab: a mail list, not a conversation, laid out like the Bulletins tab. At the top the one button Check email (`get`: the gateway sends again the mail it kept for this station; off while the radio of email is
// not connected, while there is none, or while a `get` is still being sent, the title says why), where more than one radio is on the tag of that radio (the daemon's `email_radio`: the main radio when internet gateways hear
// its kind, else the first such radio that is on; never HF), and an (i). The list (EmailList) fills the tab between them: the mail we sent with its state, and what the gateway EMAIL-2 sent us, the oldest first and scrolled to the newest, as Messages. At the bottom the box to
// write a mail in is always there (EmailCompose). The page sends it all as messages to EMAIL-2 (composables/useEmail.ts).
import { computed } from "vue";
import EmailCompose from "@/components/EmailCompose.vue";
import EmailList from "@/components/EmailList.vue";
import InfoTip from "@/components/InfoTip.vue";
import { t } from "@/i18n";
import TagMark from "@/components/TagMark.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { linkReason, radioTone } from "@/composables/useStationRadio";
import { checkingMail } from "@/lib/email";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ thread: readonly MessageRow[]; addresses: readonly string[]; freshAfter?: number }>(), {
  freshAfter: Number.MAX_SAFE_INTEGER,
});
const { heardDirect } = useDaemonContext();
const emit = defineEmits<{
  send: [to: string, text: string];
  forget: [name: string];
  get: [];
  retry: [id: number];
  cancel: [id: number];
  delete: [id: number];
}>();

const radios = useRadios();
/** The radio email goes on (internet gateways hear it); null while there is none. */
const mail = computed(() => radios.email.value);
const named = computed(() => mail.value !== null && radios.named(mail.value.id));
/** Why email cannot go: no radio internet gateways hear is on, or its link is down; undefined while it can. */
const offline = computed(() => (mail.value === null ? t("email.fm_off") : linkReason(mail.value, named.value)));
const checking = computed(() => checkingMail(props.thread));
const away = computed(() => offline.value ?? (checking.value ? t("email.checking") : undefined));
</script>

<template>
  <div class="mailpane">
    <div class="mail-bar">
      <button type="button" class="btn" :disabled="away !== undefined" :title="away" @click="emit('get')">{{ t("email.check") }}</button>
      <TagMark v-if="named && mail" class="mail-radio" :tone="radioTone(mail)" :title="t('email.radio_title', { name: mail.name })">{{ mail.name }}</TagMark>
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
