<script setup lang="ts">
// The Email tab: a mail list, not a conversation, laid out like the Bulletins tab. At the top the one button Check email (`get`: the gateway sends again the mail it kept for this station; off while the TNC is not connected or a `get` is still being
// sent, the title says why) and an (i). The list (EmailList) fills the tab between them: the mail we sent with its state, and what the gateway EMAIL-2 sent us, the oldest first and scrolled to the newest, as Messages. At the bottom the box to
// write a mail in is always there (EmailCompose). The page sends it all as messages to EMAIL-2 (composables/useEmail.ts).
import { computed } from "vue";
import EmailCompose from "@/components/EmailCompose.vue";
import EmailList from "@/components/EmailList.vue";
import InfoTip from "@/components/InfoTip.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { TNC_NOT_CONNECTED } from "@/lib/compose";
import { checkingMail } from "@/lib/email";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ thread: readonly MessageRow[]; addresses: readonly string[]; freshAfter?: number }>(), {
  freshAfter: Number.MAX_SAFE_INTEGER,
});
const { connected, heardDirect } = useDaemonContext();
const emit = defineEmits<{
  send: [to: string, text: string];
  forget: [name: string];
  get: [];
  retry: [id: number];
  cancel: [id: number];
  delete: [id: number];
}>();

const checking = computed(() => checkingMail(props.thread));
const away = computed(() => (!connected.value ? TNC_NOT_CONNECTED : checking.value ? "Already checking" : undefined));
</script>

<template>
  <div class="mailpane">
    <div class="mail-bar">
      <button type="button" class="btn" :disabled="away !== undefined" :title="away" @click="emit('get')">Check email</button>
      <span class="grow" />
      <InfoTip label="About email">
        <span class="info-line">Mail goes through the internet gateway EMAIL-2 via an iGate, so a mail can show Not confirmed although it arrived.</span>
        <span class="info-line">Check email asks the gateway for mail it kept for you (it keeps mail for 24 hours).</span>
      </InfoTip>
    </div>
    <EmailList
      :thread="thread"
      :fresh-after="freshAfter"
      :heard-direct="heardDirect"
      @retry="emit('retry', $event)"
      @cancel="emit('cancel', $event)"
      @delete="emit('delete', $event)"
    />
    <EmailCompose :connected="connected" :addresses="addresses" @send="(to, text) => emit('send', to, text)" @forget="emit('forget', $event)" />
  </div>
</template>
