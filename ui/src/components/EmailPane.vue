<script setup lang="ts">
// The Email tab: "Send an email" (EmailCompose), the mailbox and shortcut actions (EmailMailbox) and under them the thread with the gateway EMAIL-2 (MessageThread): every message to it and
// from it, the gateway's answers marked as its own, and a mail whose ack never came back "sent, not confirmed". The page sends all of it as messages to EMAIL-2 (composables/useEmail.ts).
import EmailCompose from "@/components/EmailCompose.vue";
import EmailMailbox from "@/components/EmailMailbox.vue";
import MessageThread from "@/components/MessageThread.vue";
import { EMAIL_GATEWAY } from "@/lib/messages";
import type { MessageRow } from "@/protocol/protocol";

withDefaults(defineProps<{ thread: readonly MessageRow[]; connected: boolean; addresses: readonly string[]; heardDirect?: ReadonlySet<string> }>(), {
  heardDirect: () => new Set<string>(),
});
const emit = defineEmits<{
  send: [to: string, text: string];
  forget: [name: string];
  register: [name: string, address: string];
  list: [name: string];
  remove: [name: string];
  get: [];
  retry: [id: number];
  cancel: [id: number];
}>();
</script>

<template>
  <div class="mailpane">
    <EmailCompose :connected="connected" :addresses="addresses" @send="(to, text) => emit('send', to, text)" @forget="emit('forget', $event)" />
    <EmailMailbox
      :connected="connected"
      @register="(name, address) => emit('register', name, address)"
      @list="emit('list', $event)"
      @remove="emit('remove', $event)"
      @get="emit('get')"
    />
    <MessageThread :thread="thread" :peer="EMAIL_GATEWAY" :heard-direct="heardDirect" gateway @retry="emit('retry', $event)" @cancel="emit('cancel', $event)" />
  </div>
</template>
