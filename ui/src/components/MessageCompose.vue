<script setup lang="ts">
// The box to write a message in, under the thread: "To" is filled in when a conversation is opened (or from the station card) and emptied when none is (red when it is no call); the box shows how many of
// the 67 bytes a message may have are left, and Send is off while the TNC is not connected (its title says so) or the message is empty, too long or for no call; the email gateway EMAIL-2 is no call to write to here (its title says "Use the Email tab"). The text is cleared once it is sent.
import { computed, ref, watch } from "vue";
import { normalizeCall, validCall } from "@/lib/calls";
import { bytesLeft, canSend, isGateway, replyTo } from "@/lib/messages";

const props = defineProps<{ selected: string | null; connected: boolean }>();
const emit = defineEmits<{ send: [to: string, text: string] }>();

const to = ref(props.selected === null ? "" : replyTo(props.selected));
const text = ref("");

const left = computed(() => bytesLeft(text.value));
const ready = computed(() => canSend(props.connected, to.value, text.value));
const gateway = computed(() => isGateway(to.value));
const badCall = computed(() => to.value.trim() !== "" && (!validCall(to.value) || gateway.value));
const sendTitle = computed(() => (!props.connected ? "The TNC is not connected" : gateway.value ? "Use the Email tab" : undefined));

watch(
  () => props.selected,
  (call) => {
    to.value = call === null ? "" : replyTo(call);
  },
);

function submit(): void {
  if (!ready.value) return;
  const call = normalizeCall(to.value);
  to.value = call;
  emit("send", call, text.value);
  text.value = "";
}
</script>

<template>
  <form class="compose" @submit.prevent="submit">
    <div class="compose-row">
      <label class="sr-only" for="msg-to">To</label>
      <input
        id="msg-to"
        v-model="to"
        class="input mono compose-to"
        :class="{ invalid: badCall }"
        type="text"
        placeholder="To"
        maxlength="9"
        autocomplete="off"
        spellcheck="false"
      />
      <span class="compose-left mono" :class="{ over: left < 0 }" :title="`${left} of 67 bytes left`">{{ left }}</span>
      <button type="submit" class="btn primary" :disabled="!ready" :title="sendTitle">Send</button>
    </div>
    <label class="sr-only" for="msg-text">Message</label>
    <input id="msg-text" v-model="text" class="input compose-text" type="text" placeholder="Message" autocomplete="off" />
  </form>
</template>
