<script setup lang="ts">
// "New email", the form that the button at the top of the Email tab opens at the bottom of the tab (ComposeBar, as everywhere): To (an address, or the name of a contact; while the box has the focus the suggestions are listed under it, the ones that match what is typed: the contacts
// first, each with its address, then the addresses used before, with a trash can that forgets one; a click picks one; the list opens upward, over the mail), the text, and how many of the 67 characters the line "address text" may still have, the address and the space counting.
// `to` is the addressee it opens with (the Mail button of a contact). Send is off while the TNC is not connected (its title says so) or the address or the text is empty or the line is too long; Send and Cancel both leave the form to the tab, which closes it.
import { computed, onMounted, ref } from "vue";
import ComposeBar from "@/components/ComposeBar.vue";
import IconButton from "@/components/IconButton.vue";
import type { Contact } from "@/lib/contacts";
import { canSendEmail, emailBytesLeft } from "@/lib/email";
import { MESSAGE_TEXT_MAX } from "@/protocol/lists";

const props = withDefaults(defineProps<{ connected: boolean; addresses: readonly string[]; contacts?: readonly Contact[]; to?: string }>(), {
  contacts: () => [],
  to: "",
});
const emit = defineEmits<{ send: [to: string, text: string]; forget: [name: string]; cancel: [] }>();

const to = ref(props.to);
const text = ref("");
const toBox = ref<HTMLInputElement | null>(null);
const textBox = ref<HTMLInputElement | null>(null);
const listed = ref(false);

const left = computed(() => emailBytesLeft(to.value, text.value));
const ready = computed(() => canSendEmail(props.connected, to.value, text.value));
/** The contacts that match what is typed (by name or address), other than the one whose name is typed whole. */
const people = computed(() => {
  const typed = to.value.trim().toLowerCase();
  return props.contacts.filter((c) => c.name.toLowerCase() !== typed && (c.name.toLowerCase().includes(typed) || c.address.toLowerCase().includes(typed)));
});
/** The addressees used before that match what is typed, other than the one that is typed whole and the names of contacts, who are listed above. */
const used = computed(() => {
  const typed = to.value.trim().toLowerCase();
  const names = new Set(props.contacts.map((c) => c.name.toLowerCase()));
  return props.addresses.filter((a) => a.toLowerCase() !== typed && !names.has(a.toLowerCase()) && a.toLowerCase().includes(typed));
});
const shown = computed(() => listed.value && people.value.length + used.value.length > 0);

function pick(address: string): void {
  to.value = address;
  listed.value = false;
  textBox.value?.focus();
}

function leave(event: FocusEvent): void {
  const into = event.relatedTarget;
  if (!(into instanceof Node) || !(event.currentTarget instanceof Node) || !event.currentTarget.contains(into)) listed.value = false;
}

/** Esc closes the list of suggestions when one is shown, else the form. */
function escape(): void {
  if (shown.value) listed.value = false;
  else emit("cancel");
}

function submit(): void {
  if (ready.value) emit("send", to.value.trim(), text.value);
}

onMounted(() => (props.to === "" ? toBox : textBox).value?.focus());
</script>

<template>
  <ComposeBar
    class="mailform"
    label="New email"
    :left="left"
    :left-title="`${left} of ${MESSAGE_TEXT_MAX} characters left; the address and the space count too`"
    @submit="submit"
    @keydown.esc.stop="escape"
  >
    <div class="mailfields">
      <label for="mail-to">To</label>
      <div class="mail-address" @focusout="leave">
        <input
          id="mail-to"
          ref="toBox"
          v-model="to"
          class="input mono"
          type="text"
          placeholder="Name or address"
          autocomplete="off"
          spellcheck="false"
          @focus="listed = true"
          @input="listed = true"
        />
        <ul v-if="shown" class="suggestions" aria-label="Suggestions" @mousedown.prevent>
          <li v-for="c in people" :key="`c-${c.name}`" class="suggestion contact-pick">
            <button type="button" class="suggestion-pick" @click="pick(c.name)">
              <span class="mono">{{ c.name }}</span>
              <span class="suggestion-hint mono muted">{{ c.address }}</span>
            </button>
          </li>
          <li v-for="a in used" :key="`a-${a}`" class="suggestion">
            <button type="button" class="suggestion-pick mono" @click="pick(a)">{{ a }}</button>
            <IconButton kind="delete" :label="`Forget ${a}`" :title="`Forget ${a}`" @click="emit('forget', a)" />
          </li>
        </ul>
      </div>
      <label for="mail-text">Text</label>
      <input id="mail-text" ref="textBox" v-model="text" class="input" type="text" placeholder="Text" autocomplete="off" />
    </div>
    <template #buttons>
      <button type="button" class="btn" @click="emit('cancel')">Cancel</button>
      <button type="submit" class="btn primary" :disabled="!ready" :title="connected ? undefined : 'The TNC is not connected'">Send</button>
    </template>
  </ComposeBar>
</template>
