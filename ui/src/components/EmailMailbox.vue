<script setup lang="ts">
// The gateway's other actions, under the compose box, named for what they do; the command each one sends is its hover title. "Mailbox": "Fetch held mail" (`get`: the gateway sends again the mail it holds
// for this station) and the gateway's count of attempts (the same field as a station's). "Shortcuts": a shortcut is a name the gateway keeps for an address, made by sending `name address` ("Register") and
// used as the addressee; "Email the list" (`name L`: the gateway emails the list of the shortcuts to this shortcut's address) and "Remove" (`name R`, after "sure?", forgotten after 5 s) work only for a name
// that was registered, so they stay off until "Your shortcut" holds a name. All are off while the TNC is not connected (the title says so). The page sends them as messages to the gateway; what it answers is in the thread.
import { computed, ref } from "vue";
import StationAttempts from "@/components/StationAttempts.vue";
import { useSure } from "@/composables/useSure";
import type { Attempts } from "@/lib/attempts";
import { GET_HELD, listShortcuts, removeShortcut, validAddress, validShortcut } from "@/lib/email";
import { EMAIL_GATEWAY } from "@/lib/messages";

const props = defineProps<{ connected: boolean; attempts: Attempts }>();
const emit = defineEmits<{
  register: [name: string, address: string];
  list: [name: string];
  remove: [name: string];
  get: [];
  setAttempts: [call: string, attempts: number];
  clearAttempts: [call: string];
}>();
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
  <div class="mail-tools">
    <div class="mail-row">
      <strong>Mailbox</strong>
      <button
        type="button"
        class="btn small"
        :disabled="!connected"
        :title="away ?? `Sends '${GET_HELD}': the gateway sends again the mail it holds for you`"
        @click="emit('get')"
      >
        Fetch held mail
      </button>
      <StationAttempts :call="EMAIL_GATEWAY" :attempts="attempts" @set="(c, n) => emit('setAttempts', c, n)" @clear="emit('clearAttempts', $event)" />
    </div>
    <form class="mail-shortcut" @submit.prevent="register">
      <strong class="mail-shortcut-head">Shortcut</strong>
      <label class="path-label" for="mail-shortcut">Name</label>
      <input id="mail-shortcut" v-model="name" class="input mono" type="text" placeholder="john" autocomplete="off" spellcheck="false" />
      <label class="path-label" for="mail-address">Address</label>
      <input id="mail-address" v-model="address" class="input mono" type="text" placeholder="only to register it" autocomplete="off" spellcheck="false" />
      <div class="mail-shortcut-buttons">
        <button
          type="submit"
          class="btn small"
          :disabled="!canRegister"
          :title="away ?? `Sends '${name.trim() || 'name'} ${address.trim() || 'address'}': the gateway keeps the address under the name`"
        >
          Register
        </button>
        <button
          type="button"
          class="btn small"
          :disabled="!known"
          :title="titleFor(`Sends '${listShortcuts(name)}': the gateway emails the list of your shortcuts to this shortcut's address`)"
          @click="emit('list', name.trim())"
        >
          Email the list
        </button>
        <button
          type="button"
          class="btn small"
          :class="{ danger: armed }"
          :disabled="!known"
          :title="titleFor(`Sends '${removeShortcut(name)}': the gateway removes this shortcut`)"
          @click="remove"
        >
          {{ armed ? "sure?" : "Remove" }}
        </button>
      </div>
    </form>
  </div>
</template>
