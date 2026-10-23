<script setup lang="ts">
// The Email tab: a mail list, not a conversation. At the top the button "New email" (it opens EmailCompose, which closes with Send or Cancel), the menu "Mailbox" (Fetch held mail, Shortcuts…, which opens EmailShortcuts) and an (i) that
// says once why a mail may be "Not confirmed". Under them the list (EmailList): the mail we sent with its state, and what the gateway EMAIL-2 sent us, newest first. The page sends it all as messages to EMAIL-2 (composables/useEmail.ts).
import { ref } from "vue";
import EmailCompose from "@/components/EmailCompose.vue";
import EmailList from "@/components/EmailList.vue";
import EmailMailbox from "@/components/EmailMailbox.vue";
import EmailShortcuts from "@/components/EmailShortcuts.vue";
import InfoTip from "@/components/InfoTip.vue";
import type { MessageRow } from "@/protocol/protocol";

withDefaults(
  defineProps<{ thread: readonly MessageRow[]; connected: boolean; addresses: readonly string[]; freshAfter?: number; heardDirect?: ReadonlySet<string> }>(),
  {
    freshAfter: Number.MAX_SAFE_INTEGER,
    heardDirect: () => new Set<string>(),
  },
);
const emit = defineEmits<{
  send: [to: string, text: string];
  forget: [name: string];
  register: [name: string, address: string];
  list: [name: string];
  remove: [name: string];
  get: [];
  retry: [id: number];
  cancel: [id: number];
  delete: [id: number];
}>();

/** The form that is open under the buttons: one at a time. */
const form = ref<"new" | "shortcuts" | null>(null);

function send(to: string, text: string): void {
  emit("send", to, text);
  form.value = null;
}
</script>

<template>
  <div class="mailpane">
    <div class="mail-bar">
      <button type="button" class="btn primary" :aria-expanded="form === 'new'" @click="form = form === 'new' ? null : 'new'">New email</button>
      <EmailMailbox :connected="connected" @get="emit('get')" @shortcuts="form = 'shortcuts'" />
      <span class="grow" />
      <InfoTip label="About email">
        <span class="info-line">Mail goes to the email gateway EMAIL-2 on the internet, through an iGate that hears your radio.</span>
        <span class="info-line">The gateway's answers come back the same way, so a mail may say Not confirmed although it went through.</span>
      </InfoTip>
    </div>
    <EmailCompose v-if="form === 'new'" :connected="connected" :addresses="addresses" @send="send" @forget="emit('forget', $event)" @cancel="form = null" />
    <EmailShortcuts
      v-else-if="form === 'shortcuts'"
      :connected="connected"
      @register="(name, address) => emit('register', name, address)"
      @list="emit('list', $event)"
      @remove="emit('remove', $event)"
      @close="form = null"
    />
    <div class="maillist-wrap">
      <EmailList
        :thread="thread"
        :fresh-after="freshAfter"
        :heard-direct="heardDirect"
        @retry="emit('retry', $event)"
        @cancel="emit('cancel', $event)"
        @delete="emit('delete', $event)"
      />
    </div>
  </div>
</template>
