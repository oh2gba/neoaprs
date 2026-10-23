<script setup lang="ts">
// The Email tab: a mail list, not a conversation. At the top three buttons of one size, New email (it opens EmailCompose, which closes with Send or Cancel), Contacts (it opens EmailContacts, the people this station mails by name and who may
// mail it) and Check for mail (`get`: the gateway sends again the mail it kept for this station; off while the TNC is not connected or a `get` is still being sent, the title says why), and an (i). One panel is open at a time, in place
// under the buttons. Under them the list (EmailList): the mail we sent with its state, and what the gateway EMAIL-2 sent us, newest first. The page sends it all as messages to EMAIL-2 (composables/useEmail.ts).
import { computed, ref } from "vue";
import EmailCompose from "@/components/EmailCompose.vue";
import EmailContacts from "@/components/EmailContacts.vue";
import EmailList from "@/components/EmailList.vue";
import InfoTip from "@/components/InfoTip.vue";
import { contactsOf } from "@/lib/contacts";
import { checkingMail } from "@/lib/email";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{ thread: readonly MessageRow[]; connected: boolean; addresses: readonly string[]; freshAfter?: number; heardDirect?: ReadonlySet<string> }>(),
  {
    freshAfter: Number.MAX_SAFE_INTEGER,
    heardDirect: () => new Set<string>(),
  },
);
const emit = defineEmits<{
  send: [to: string, text: string];
  forget: [name: string];
  add: [name: string, address: string];
  list: [name: string];
  remove: [name: string];
  get: [];
  retry: [id: number];
  cancel: [id: number];
  delete: [id: number];
}>();

const contacts = computed(() => contactsOf(props.thread));
const checking = computed(() => checkingMail(props.thread));
const away = computed(() => (!props.connected ? "The TNC is not connected" : checking.value ? "Already checking" : undefined));

/** The panel that is open under the buttons: one at a time. */
const form = ref<"new" | "contacts" | null>(null);
/** The addressee New email opens with (the Mail button of a contact). */
const writeTo = ref("");

function toggle(which: "new" | "contacts"): void {
  writeTo.value = "";
  form.value = form.value === which ? null : which;
}

function mailTo(name: string): void {
  writeTo.value = name;
  form.value = "new";
}

function send(to: string, text: string): void {
  emit("send", to, text);
  form.value = null;
}
</script>

<template>
  <div class="mailpane">
    <div class="mail-bar">
      <button type="button" class="btn primary" :aria-expanded="form === 'new'" @click="toggle('new')">New email</button>
      <button type="button" class="btn" :aria-expanded="form === 'contacts'" @click="toggle('contacts')">Contacts</button>
      <button type="button" class="btn" :disabled="away !== undefined" :title="away" @click="emit('get')">Check for mail</button>
      <span class="grow" />
      <InfoTip label="About email">
        <span class="info-line">Mail goes through the internet gateway EMAIL-2 via an iGate, so a mail can say Not confirmed although it arrived.</span>
        <span class="info-line">Only your contacts can email you; their mail arrives here.</span>
        <span class="info-line">If your radio missed one, Check for mail asks the gateway to send again what it kept (it keeps mail for 24 hours).</span>
      </InfoTip>
    </div>
    <EmailCompose
      v-if="form === 'new'"
      :connected="connected"
      :addresses="addresses"
      :contacts="contacts"
      :to="writeTo"
      @send="send"
      @forget="emit('forget', $event)"
      @cancel="form = null"
    />
    <EmailContacts
      v-else-if="form === 'contacts'"
      :connected="connected"
      :contacts="contacts"
      @add="(name, address) => emit('add', name, address)"
      @list="emit('list', $event)"
      @remove="emit('remove', $event)"
      @mail="mailTo"
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
