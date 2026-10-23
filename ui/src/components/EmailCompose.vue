<script setup lang="ts">
// "New email", the small form that the button at the top of the Email tab opens: To (an address, or the name of a shortcut registered with the gateway; while the box has the focus the addressees used before are listed under it, the
// ones that match what is typed, a click picks one and the trash can beside it forgets it), the text, and how many of the 67 characters the line "address text" may still have, the address and the space counting. Send is off while the
// TNC is not connected (its title says so) or the address or the text is empty or the line is too long; Send and Cancel both leave the form to the tab, which closes it.
import { computed, onMounted, ref } from "vue";
import IconButton from "@/components/IconButton.vue";
import { canSendEmail, emailBytesLeft } from "@/lib/email";
import { leftText } from "@/lib/format";
import { MESSAGE_TEXT_MAX } from "@/protocol/lists";

const props = defineProps<{ connected: boolean; addresses: readonly string[] }>();
const emit = defineEmits<{ send: [to: string, text: string]; forget: [name: string]; cancel: [] }>();

const to = ref("");
const text = ref("");
const toBox = ref<HTMLInputElement | null>(null);
const textBox = ref<HTMLInputElement | null>(null);
const listed = ref(false);

const left = computed(() => emailBytesLeft(to.value, text.value));
const ready = computed(() => canSendEmail(props.connected, to.value, text.value));
/** The addressees used before that match what is typed, other than the one that is typed whole. */
const suggestions = computed(() => {
  const typed = to.value.trim().toLowerCase();
  return props.addresses.filter((a) => a.toLowerCase() !== typed && a.toLowerCase().includes(typed));
});

function pick(address: string): void {
  to.value = address;
  listed.value = false;
  textBox.value?.focus();
}

function leave(event: FocusEvent): void {
  const into = event.relatedTarget;
  if (!(into instanceof Node) || !(event.currentTarget instanceof Node) || !event.currentTarget.contains(into)) listed.value = false;
}

/** Esc closes the list of addressees when one is shown, else the form. */
function escape(): void {
  if (listed.value && suggestions.value.length > 0) listed.value = false;
  else emit("cancel");
}

function submit(): void {
  if (ready.value) emit("send", to.value.trim(), text.value);
}

onMounted(() => toBox.value?.focus());
</script>

<template>
  <form class="mailform" aria-label="New email" @submit.prevent="submit" @keydown.esc.stop="escape">
    <label for="mail-to">To</label>
    <div class="mail-address" @focusout="leave">
      <input
        id="mail-to"
        ref="toBox"
        v-model="to"
        class="input mono"
        type="text"
        placeholder="Address or shortcut"
        autocomplete="off"
        spellcheck="false"
        @focus="listed = true"
        @input="listed = true"
      />
      <ul v-if="listed && suggestions.length > 0" class="suggestions" aria-label="Used before" @mousedown.prevent>
        <li v-for="a in suggestions" :key="a" class="suggestion">
          <button type="button" class="suggestion-pick mono" @click="pick(a)">{{ a }}</button>
          <IconButton kind="delete" :label="`Forget ${a}`" :title="`Forget ${a}`" @click="emit('forget', a)" />
        </li>
      </ul>
    </div>
    <label for="mail-text">Text</label>
    <input id="mail-text" ref="textBox" v-model="text" class="input" type="text" placeholder="Text" autocomplete="off" />
    <div class="mailform-actions">
      <span
        class="compose-left mono"
        :class="{ over: left < 0 }"
        :title="`${left} of ${MESSAGE_TEXT_MAX} characters left; the address and the space count too`"
        >{{ leftText(left) }}</span
      >
      <button type="button" class="btn" @click="emit('cancel')">Cancel</button>
      <button type="submit" class="btn primary" :disabled="!ready" :title="connected ? undefined : 'The TNC is not connected'">Send</button>
    </div>
  </form>
</template>
