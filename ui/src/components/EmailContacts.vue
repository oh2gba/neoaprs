<script setup lang="ts">
// "Contacts", the panel that the button of that name opens in the Email tab: the people this station mails by name and who may mail it (the gateway's shortcuts; lib/contacts.ts reads them from our messages to it). Each has
// Mail (opens New email addressed to the name), Email me the list (`name L`: the gateway emails the list of the contacts to this contact's address) and Remove (`name R`, after "sure?", forgotten after 5 s); under the list
// is the form that adds one (`name address`). Everything that sends is off while the TNC is not connected (the title says so); the command each one sends is its hover title.
import { computed, ref } from "vue";
import ComposeBar from "@/components/ComposeBar.vue";
import { useSure } from "@/composables/useSure";
import type { Contact } from "@/lib/contacts";
import { canSendEmail, listContacts, removeContact, validAddress, validContact } from "@/lib/email";

const props = defineProps<{ connected: boolean; contacts: readonly Contact[] }>();
const emit = defineEmits<{ add: [name: string, address: string]; list: [name: string]; remove: [name: string]; mail: [name: string]; close: [] }>();
const sure = useSure<string>(); // (the contact that is to be removed)

const name = ref("");
const address = ref("");
const away = computed(() => (props.connected ? undefined : "The TNC is not connected"));
const ready = computed(() => canSendEmail(props.connected, name.value, address.value) && validContact(name.value) && validAddress(address.value));

const WAITING = "Not confirmed: the gateway's ack reaches you only through an iGate, so it may well have the contact";

function add(): void {
  if (!ready.value) return;
  emit("add", name.value.trim(), address.value.trim());
  name.value = "";
  address.value = "";
}
</script>

<template>
  <section class="contacts" aria-label="Contacts" @keydown.esc.stop="emit('close')">
    <ul v-if="contacts.length > 0" class="contact-list">
      <li v-for="c in contacts" :key="c.name.toLowerCase()" class="contact">
        <div class="contact-who">
          <span class="contact-name">{{ c.name }}</span>
          <span class="contact-address mono">{{ c.address }}</span>
          <span v-if="c.state === 'unconfirmed'" class="contact-state muted" :title="WAITING">Not confirmed</span>
          <span v-else-if="c.state === 'sending'" class="contact-state muted">Sending</span>
        </div>
        <div class="contact-actions">
          <button type="button" class="btn small" :title="`Write to ${c.name}`" @click="emit('mail', c.name)">Mail</button>
          <button
            type="button"
            class="btn small"
            :disabled="!connected"
            :title="away ?? `Sends '${listContacts(c.name)}': the gateway emails the list of your contacts to ${c.address}`"
            @click="emit('list', c.name)"
          >
            Email me the list
          </button>
          <button
            type="button"
            class="btn small"
            :class="{ danger: sure.armed.value === c.name.toLowerCase() }"
            :disabled="!connected"
            :title="away ?? `Sends '${removeContact(c.name)}': the gateway forgets ${c.name}`"
            @click="sure.press(c.name.toLowerCase(), () => emit('remove', c.name))"
          >
            {{ sure.armed.value === c.name.toLowerCase() ? "sure?" : "Remove" }}
          </button>
        </div>
      </li>
    </ul>
    <p v-else class="empty">No contacts yet.</p>
    <ComposeBar class="contact-add" label="Add contact" @submit="add">
      <div class="mailfields">
        <label for="contact-name">Name</label>
        <input id="contact-name" v-model="name" class="input mono" type="text" placeholder="john" autocomplete="off" spellcheck="false" />
        <label for="contact-address">Address</label>
        <input id="contact-address" v-model="address" class="input mono" type="text" placeholder="name@example.com" autocomplete="off" spellcheck="false" />
      </div>
      <template #buttons>
        <button type="button" class="btn" @click="emit('close')">Close</button>
        <button
          type="submit"
          class="btn primary"
          :disabled="!ready"
          :title="away ?? `Sends '${name.trim() || 'name'} ${address.trim() || 'address'}': the gateway keeps the address under the name`"
        >
          Add contact
        </button>
      </template>
    </ComposeBar>
  </section>
</template>
