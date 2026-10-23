<script setup lang="ts">
// The Email tab: the box to write mail in (EmailCompose), the gateway's commands and its attempts (EmailCommands) and under them the thread with the gateway EMAIL-2 (MessageThread): every message to it and from it, so its acks
// and its answers to `name L` and `get` are read where the mail was sent. The page sends all of it as messages to EMAIL-2 (composables/useEmail.ts).
import { ref } from "vue";
import EmailCommands from "@/components/EmailCommands.vue";
import EmailCompose from "@/components/EmailCompose.vue";
import MessageThread from "@/components/MessageThread.vue";
import type { Attempts } from "@/lib/attempts";
import { EMAIL_GATEWAY } from "@/lib/messages";
import type { MessageRow } from "@/protocol/protocol";

withDefaults(
  defineProps<{ thread: readonly MessageRow[]; connected: boolean; addresses: readonly string[]; attempts: Attempts; heardDirect?: ReadonlySet<string> }>(),
  {
    heardDirect: () => new Set<string>(),
  },
);
const emit = defineEmits<{
  send: [to: string, text: string];
  forget: [name: string];
  list: [name: string];
  remove: [name: string];
  get: [];
  setAttempts: [call: string, attempts: number];
  clearAttempts: [call: string];
  retry: [id: number];
  cancel: [id: number];
}>();

const to = ref("");
</script>

<template>
  <div class="mailpane">
    <EmailCompose v-model:to="to" :connected="connected" :addresses="addresses" @send="(to, text) => emit('send', to, text)" @forget="emit('forget', $event)" />
    <EmailCommands
      :connected="connected"
      :to="to"
      :attempts="attempts"
      @list="emit('list', $event)"
      @remove="emit('remove', $event)"
      @get="emit('get')"
      @set-attempts="(c, n) => emit('setAttempts', c, n)"
      @clear-attempts="emit('clearAttempts', $event)"
    />
    <MessageThread :thread="thread" :peer="EMAIL_GATEWAY" :heard-direct="heardDirect" @retry="emit('retry', $event)" @cancel="emit('cancel', $event)" />
  </div>
</template>
