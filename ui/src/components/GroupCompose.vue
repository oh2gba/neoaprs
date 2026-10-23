<script setup lang="ts">
// One text to several stations, in the place of a conversation: the header has the recipients as chips (a click on one, or its ×, takes it out; the last one out closes the view), a close button and on a narrow page the back arrow "‹"; under it the quiet room where a
// thread would be, and at the bottom the box to write in with "12 left" and "Send to 3" (MessageCompose). It is opened by the page with a list of calls (composables/useMessagesView.ts `openGroup`, from the map's station cards) and is no conversation: it sends one ordinary
// message to each recipient and closes, and the conversations appear in the list as the messages go out. Esc closes it, as the back arrow does on a narrow page.
import { onMounted, ref } from "vue";
import IconButton from "@/components/IconButton.vue";
import MessageCompose from "@/components/MessageCompose.vue";
import { t } from "@/i18n";

const props = defineProps<{ calls: readonly string[]; narrow: boolean; connected: boolean }>();
const text = defineModel<string>("text", { default: "" });
const emit = defineEmits<{
  /** the recipients that are left (a call was taken out) */
  update: [calls: string[]];
  /** the view was closed (the back arrow, the close button, Esc) */
  close: [];
  send: [to: string, text: string];
  sendMany: [to: string[], text: string];
}>();

const compose = ref<InstanceType<typeof MessageCompose> | null>(null);

onMounted(() => {
  compose.value?.focusText();
});

function take(call: string): void {
  const left = props.calls.filter((c) => c !== call);
  if (left.length === 0) emit("close");
  else emit("update", left);
}
</script>

<template>
  <section class="convo group" :aria-label="t('messages.group')">
    <header class="convo-head group-head">
      <button v-if="narrow" type="button" class="convo-back" :aria-label="t('messages.back_label')" :title="t('messages.back')" @click="emit('close')">
        <span aria-hidden="true">‹</span>
      </button>
      <ul class="recipients" :aria-label="t('messages.recipients')">
        <li v-for="call in calls" :key="call">
          <button type="button" class="chip" :aria-label="t('messages.remove_label', { call })" :title="t('messages.remove')" @click="take(call)">
            {{ call }} &times;
          </button>
        </li>
      </ul>
      <IconButton v-if="!narrow" kind="close" :label="t('messages.close')" @click="emit('close')" />
    </header>
    <div class="group-room"></div>
    <MessageCompose
      ref="compose"
      v-model:text="text"
      :to="calls"
      :connected="connected"
      @send="(to, body) => emit('send', to, body)"
      @send-many="(to, body) => emit('sendMany', to, body)"
    />
  </section>
</template>
