<script setup lang="ts">
// The box to write a message in, fixed at the bottom of a conversation: the text, how many of the 67 bytes a message may have are left ("67 left") and Send, in one line. There is no To: the conversation is the station (`to` is its call), or for a group (GroupCompose) the
// calls that were picked, and then Send says "Send to 3". Send is off while the TNC is not connected (its title says so) or the text is empty or too long (lib/recipients.ts `canSendAll`). With one recipient it says `send`; with several it says `sendMany`, which the
// page turns into one ordinary message to each. The text is cleared once it is sent.
import { computed, ref } from "vue";
import { leftText } from "@/lib/format";
import { bytesLeft } from "@/lib/messages";
import { canSendAll } from "@/lib/recipients";

const props = defineProps<{ to: readonly string[]; connected: boolean }>();
const emit = defineEmits<{ send: [to: string, text: string]; sendMany: [to: string[], text: string] }>();

/** The text being written: the page's to keep, so that a draft stays when the user goes back to the list and in again. */
const text = defineModel<string>("text", { default: "" });
const input = ref<HTMLInputElement | null>(null);

const left = computed(() => bytesLeft(text.value));
const ready = computed(() => canSendAll(props.connected, props.to, "", text.value));
const sendLabel = computed(() => (props.to.length > 1 ? `Send to ${props.to.length}` : "Send"));
const sendTitle = computed(() => (props.connected ? undefined : "The TNC is not connected"));

defineExpose({ focusText: (): void => input.value?.focus() });

function submit(): void {
  if (!ready.value) return;
  const [only] = props.to;
  if (props.to.length === 1 && only !== undefined) emit("send", only, text.value);
  else emit("sendMany", [...props.to], text.value);
  text.value = "";
}
</script>

<template>
  <form class="compose" @submit.prevent="submit">
    <label class="sr-only" for="msg-text">Message</label>
    <input id="msg-text" ref="input" v-model="text" class="input compose-text grow" type="text" placeholder="Message" autocomplete="off" />
    <span class="compose-left mono" :class="{ over: left < 0 }" :title="`${left} of 67 bytes left`">{{ leftText(left) }}</span>
    <button type="submit" class="btn primary" :disabled="!ready" :title="sendTitle">{{ sendLabel }}</button>
  </form>
</template>
