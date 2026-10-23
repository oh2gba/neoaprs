<script setup lang="ts">
// "Shortcuts", the form that Mailbox > Shortcuts opens: a shortcut is a name the gateway keeps for an address, made by sending `name address` ("Register") and used as the addressee. "Email the list" (`name L`: the gateway
// emails the list of the shortcuts to this shortcut's address) and "Remove" (`name R`, after "sure?", forgotten after 5 s) work only for a name that was registered, so they stay off until "Name" holds a name. All are off while
// the TNC is not connected (the title says so); the command each one sends is its hover title. The page sends them as messages to the gateway; the list shows them in words.
import { computed, ref } from "vue";
import { useSure } from "@/composables/useSure";
import { listShortcuts, removeShortcut, validAddress, validShortcut } from "@/lib/email";

const props = defineProps<{ connected: boolean }>();
const emit = defineEmits<{ register: [name: string, address: string]; list: [name: string]; remove: [name: string]; close: [] }>();
const sure = useSure<string>(); // (the shortcut that is to be removed)

const name = ref("");
const address = ref("");
const away = computed(() => (props.connected ? undefined : "The TNC is not connected"));
const known = computed(() => props.connected && validShortcut(name.value));
const canRegister = computed(() => known.value && validAddress(address.value));
const armed = computed(() => sure.armed.value === name.value.trim());

const needName = "Fill in the shortcut's Name: a name registered with the gateway";
const titleFor = (sent: string): string => away.value ?? (validShortcut(name.value) ? sent : needName);

function register(): void {
  if (!canRegister.value) return;
  emit("register", name.value.trim(), address.value.trim());
  address.value = "";
}

function remove(): void {
  if (known.value) sure.press(name.value.trim(), () => emit("remove", name.value.trim()));
}
</script>

<template>
  <form class="mailform" aria-label="Shortcuts" @submit.prevent="register" @keydown.esc.stop="emit('close')">
    <label for="mail-shortcut">Name</label>
    <input id="mail-shortcut" v-model="name" class="input mono" type="text" placeholder="john" autocomplete="off" spellcheck="false" />
    <label for="mail-address">Address</label>
    <input id="mail-address" v-model="address" class="input mono" type="text" placeholder="name@example.com" autocomplete="off" spellcheck="false" />
    <div class="mailform-actions">
      <button
        type="submit"
        class="btn primary"
        :disabled="!canRegister"
        :title="away ?? `Sends '${name.trim() || 'name'} ${address.trim() || 'address'}': the gateway keeps the address under the name`"
      >
        Register
      </button>
      <button
        type="button"
        class="btn"
        :disabled="!known"
        :title="titleFor(`Sends '${listShortcuts(name)}': the gateway emails the list of your shortcuts to this shortcut's address`)"
        @click="emit('list', name.trim())"
      >
        Email the list
      </button>
      <button
        type="button"
        class="btn"
        :class="{ danger: armed }"
        :disabled="!known"
        :title="titleFor(`Sends '${removeShortcut(name)}': the gateway removes this shortcut`)"
        @click="remove"
      >
        {{ armed ? "sure?" : "Remove" }}
      </button>
      <button type="button" class="btn" @click="emit('close')">Close</button>
    </div>
  </form>
</template>
