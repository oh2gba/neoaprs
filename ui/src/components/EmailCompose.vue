<script setup lang="ts">
// "Send an email", at the top of the Email tab: the address (or the name of a shortcut registered with the gateway), the text, and under the text the addressees used before (a click puts one in "To", the x forgets
// it). The number is how many of the 67 characters the line "address text" may still have, the address and the space counting; Send is off while the TNC is not connected (its title says so) or the address
// or the text is empty or the line is too long. The text is cleared once it is sent.
import { computed, ref } from "vue";
import { canSendEmail, emailBytesLeft } from "@/lib/email";
import { MESSAGE_TEXT_MAX } from "@/protocol/lists";

const props = defineProps<{ connected: boolean; addresses: readonly string[] }>();
const emit = defineEmits<{ send: [to: string, text: string]; forget: [name: string] }>();

const to = ref("");
const text = ref("");

const left = computed(() => emailBytesLeft(to.value, text.value));
const ready = computed(() => canSendEmail(props.connected, to.value, text.value));

function submit(): void {
  if (!ready.value) return;
  to.value = to.value.trim();
  emit("send", to.value, text.value);
  text.value = "";
}
</script>

<template>
  <form class="compose" aria-label="Send an email" @submit.prevent="submit">
    <div class="toolbar">
      <strong>Send an email</strong>
      <span class="grow" />
      <span class="compose-left mono" :class="{ over: left < 0 }" :title="`${left} of ${MESSAGE_TEXT_MAX} characters left; the address and the space count too`"
        >{{ left }} left</span
      >
    </div>
    <div class="compose-row">
      <label class="sr-only" for="mail-to">To</label>
      <input
        id="mail-to"
        v-model="to"
        class="input mono mail-to"
        type="text"
        placeholder="To: email address or shortcut"
        autocomplete="off"
        spellcheck="false"
      />
      <button type="submit" class="btn primary" :disabled="!ready" :title="connected ? undefined : 'The TNC is not connected'">Send</button>
    </div>
    <label class="sr-only" for="mail-text">Text</label>
    <input id="mail-text" v-model="text" class="input compose-text" type="text" placeholder="Text" autocomplete="off" />
    <ul v-if="addresses.length > 0" class="addresses" aria-label="Used before">
      <li v-for="a in addresses" :key="a" class="address">
        <button type="button" class="chip address-pick" @click="to = a">{{ a }}</button>
        <button type="button" class="address-forget" :title="`Forget ${a}`" :aria-label="`Forget ${a}`" @click="emit('forget', a)">x</button>
      </li>
    </ul>
  </form>
</template>
