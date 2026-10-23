<script setup lang="ts">
// The box to write an email in, always at the bottom of the Email tab (ComposeBar, as everywhere): To (an email address; while the box has the focus the addresses used before that match what is typed are listed under it, upward over the mail:
// a click picks one, the trash can beside it forgets it), the text, and how many of the characters of a message the line "address text" may still have, the address and the space counting. Send, at the lower right, is off while the TNC is not connected
// (its title says so) or the address or the text is empty or the line is too long. After Send the text is empty again and the address stays, for the next mail to the same person; the focus is in the text.
import { computed, ref } from "vue";
import ComposeBar from "@/components/ComposeBar.vue";
import IconButton from "@/components/IconButton.vue";
import { canSendEmail, emailBytesLeft } from "@/lib/email";
import { LIMITS } from "@/protocol/lists";

const props = defineProps<{ connected: boolean; addresses: readonly string[] }>();
const emit = defineEmits<{ send: [to: string, text: string]; forget: [name: string] }>();

const to = ref("");
const text = ref("");
const textBox = ref<HTMLInputElement | null>(null);
const listed = ref(false);

const left = computed(() => emailBytesLeft(to.value, text.value));
const ready = computed(() => canSendEmail(props.connected, to.value, text.value));
/** The addresses used before that match what is typed, other than the one that is typed whole. */
const suggestions = computed(() => {
  const typed = to.value.trim().toLowerCase();
  return props.addresses.filter((a) => a.toLowerCase() !== typed && a.toLowerCase().includes(typed));
});
const shown = computed(() => listed.value && suggestions.value.length > 0);

function pick(address: string): void {
  to.value = address;
  listed.value = false;
  textBox.value?.focus();
}

function leave(event: FocusEvent): void {
  const into = event.relatedTarget;
  if (!(into instanceof Node) || !(event.currentTarget instanceof Node) || !event.currentTarget.contains(into)) listed.value = false;
}

function submit(): void {
  if (!ready.value) return;
  emit("send", to.value.trim(), text.value);
  text.value = "";
  textBox.value?.focus();
}
</script>

<template>
  <ComposeBar
    class="mailform"
    label="Email"
    :left="left"
    :left-title="`${left} of ${LIMITS.message.textMax} characters left; the address and the space count too`"
    @submit="submit"
    @keydown.esc.stop="listed = false"
  >
    <div class="mailfields">
      <label for="mail-to">To</label>
      <div class="mail-address" @focusout="leave">
        <input
          id="mail-to"
          v-model="to"
          class="input mono"
          type="text"
          placeholder="Email address"
          autocomplete="off"
          spellcheck="false"
          @focus="listed = true"
          @input="listed = true"
        />
        <ul v-if="shown" class="suggestions" aria-label="Used before" @mousedown.prevent>
          <li v-for="a in suggestions" :key="a" class="suggestion">
            <button type="button" class="suggestion-pick mono" @click="pick(a)">{{ a }}</button>
            <IconButton kind="delete" :label="`Forget ${a}`" :title="`Forget ${a}`" @click="emit('forget', a)" />
          </li>
        </ul>
      </div>
      <label for="mail-text">Text</label>
      <input id="mail-text" ref="textBox" v-model="text" class="input" type="text" placeholder="Text" autocomplete="off" />
    </div>
    <template #buttons>
      <button type="submit" class="btn primary" :disabled="!ready" :title="connected ? undefined : 'The TNC is not connected'">Send</button>
    </template>
  </ComposeBar>
</template>
