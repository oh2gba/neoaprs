<script setup lang="ts">
// The box to write a message in, under the thread: "To" is filled in when a conversation is opened (or from the station card) and emptied when none is (red when it is no call); the box shows how many of
// the 67 bytes a message may have are left ("67 left"), and Send is off while the TNC is not connected (its title says so) or the message is empty, too long or for no call; the email gateway EMAIL-2 is no call to write to here (its title says "Use the Email tab"). The text is cleared once it is sent.
// "Stations" opens the list of the stations heard lately (lib/recipients.ts) with a filter and a tickbox for each: the ones ticked are shown as chips that a click removes, and a call typed in To followed by a
// space or a comma becomes a chip too, as does "Add OH2XYZ" in the list for a call that is not in it. With one recipient Send is what it always was; with several it sends one ordinary message to each (`sendMany`).
import { computed, ref, watch } from "vue";
import { normalizeCall, validCall } from "@/lib/calls";
import { leftText } from "@/lib/format";
import { bytesLeft, isGateway, replyTo } from "@/lib/messages";
import { addable, canSendAll, matching, recipientsOf, type Candidate } from "@/lib/recipients";

const props = withDefaults(defineProps<{ selected: string | null; connected: boolean; candidates?: readonly Candidate[] }>(), { candidates: () => [] });
const emit = defineEmits<{ send: [to: string, text: string]; sendMany: [to: string[], text: string] }>();

const to = ref(props.selected === null ? "" : replyTo(props.selected));
const text = ref("");
const chosen = ref<string[]>([]);
const picking = ref(false);
const filter = ref("");

const left = computed(() => bytesLeft(text.value));
const ready = computed(() => canSendAll(props.connected, chosen.value, to.value, text.value));
const gateway = computed(() => isGateway(to.value));
const badCall = computed(() => to.value.trim() !== "" && (!validCall(to.value) || gateway.value));
const sendTitle = computed(() => (!props.connected ? "The TNC is not connected" : gateway.value ? "Use the Email tab" : undefined));
const listed = computed(() => matching(props.candidates, filter.value));
const typedNew = computed(() => {
  const call = normalizeCall(filter.value);
  return addable(call, chosen.value) && !props.candidates.some((c) => c.call === call) ? call : null;
});

watch(
  () => props.selected,
  (call) => {
    to.value = call === null ? "" : replyTo(call);
    chosen.value = [];
  },
);

function ticked(call: string): boolean {
  return chosen.value.includes(call) || normalizeCall(to.value) === call;
}

/** A tick in the list or a click on a chip: the call goes into the chips, or out of them (or out of the To box when it is there). */
function toggle(call: string): void {
  if (normalizeCall(to.value) === call) to.value = "";
  else if (chosen.value.includes(call)) chosen.value = chosen.value.filter((c) => c !== call);
  else chosen.value = [...chosen.value, call];
}

function addTyped(call: string): void {
  if (addable(call, chosen.value)) chosen.value = [...chosen.value, normalizeCall(call)];
  filter.value = "";
}

/** A space or a comma after a call in the To box makes it a chip. */
function onToKey(event: KeyboardEvent): void {
  if ((event.key !== " " && event.key !== ",") || !addable(to.value, chosen.value)) return;
  event.preventDefault();
  chosen.value = [...chosen.value, normalizeCall(to.value)];
  to.value = "";
}

function submit(): void {
  if (!ready.value) return;
  const calls = recipientsOf(chosen.value, to.value);
  chosen.value = [];
  if (calls.length === 1 && calls[0] !== undefined) {
    to.value = calls[0];
    emit("send", calls[0], text.value);
  } else {
    to.value = "";
    emit("sendMany", calls, text.value);
  }
  text.value = "";
}
</script>

<template>
  <form class="compose" @submit.prevent="submit">
    <ul v-if="chosen.length > 0" class="recipients" aria-label="Recipients">
      <li v-for="call in chosen" :key="call">
        <button type="button" class="chip" :aria-label="`Remove ${call}`" title="Remove" @click="toggle(call)">{{ call }} &times;</button>
      </li>
    </ul>
    <div class="compose-row">
      <label class="sr-only" for="msg-to">To</label>
      <input
        id="msg-to"
        v-model="to"
        class="input mono compose-to"
        :class="{ invalid: badCall }"
        type="text"
        placeholder="Call"
        maxlength="9"
        autocomplete="off"
        spellcheck="false"
        @keydown="onToKey"
      />
      <button type="button" class="btn" :aria-expanded="picking" title="Write to several stations" @click="picking = !picking">Stations</button>
      <span class="compose-left mono" :class="{ over: left < 0 }" :title="`${left} of 67 bytes left`">{{ leftText(left) }}</span>
      <button type="submit" class="btn primary" :disabled="!ready" :title="sendTitle">Send</button>
    </div>
    <div v-if="picking" class="picker">
      <label class="sr-only" for="msg-filter">Filter</label>
      <input
        id="msg-filter"
        v-model="filter"
        class="input mono"
        type="text"
        placeholder="Filter"
        autocomplete="off"
        spellcheck="false"
        @keydown.enter.prevent="typedNew && addTyped(typedNew)"
      />
      <ul class="picker-list" aria-label="Stations">
        <li v-for="c in listed" :key="c.call">
          <label class="check"
            ><input type="checkbox" :checked="ticked(c.call)" @change="toggle(c.call)" /> <span class="mono">{{ c.call }}</span>
            <span v-if="c.direct" class="muted">direct</span></label
          >
        </li>
        <li v-if="typedNew">
          <button type="button" class="chip" @click="addTyped(typedNew)">Add {{ typedNew }}</button>
        </li>
        <li v-if="listed.length === 0 && !typedNew" class="empty">No station.</li>
      </ul>
    </div>
    <label class="sr-only" for="msg-text">Message</label>
    <input id="msg-text" v-model="text" class="input compose-text" type="text" placeholder="Message" autocomplete="off" />
  </form>
</template>
