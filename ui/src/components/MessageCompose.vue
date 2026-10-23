<script setup lang="ts">
// The box to write a message in, fixed at the bottom of a conversation: the text, how many of the bytes a message may have are left ("12 left") and Send, in one line (ComposeBar of one field, as on every tab). There is no To: the conversation is the station (`to` is its call), or for a group (GroupCompose) the
// calls that were picked, and then Send says "Send to 3". Send is off while the TNC is not connected (its title says so) or the text is empty or too long (lib/recipients.ts `canSendAll`). With one recipient it says `send`; with several it says `sendMany`, which the
// page turns into one ordinary message to each. The text is cleared once it is sent.
import { computed, ref } from "vue";
import ComposeBar from "@/components/ComposeBar.vue";
import { t } from "@/i18n";
import { leftTitle, sendBlockedReason } from "@/lib/compose";
import { bytesLeft } from "@/lib/messages";
import { canSendAll } from "@/lib/recipients";
import { LIMITS } from "@/protocol/lists";

const props = defineProps<{ to: readonly string[]; connected: boolean }>();
const emit = defineEmits<{ send: [to: string, text: string]; sendMany: [to: string[], text: string] }>();

/** The text being written: the page's to keep, so that a draft stays when the user goes back to the list and in again. */
const text = defineModel<string>("text", { default: "" });
const input = ref<HTMLInputElement | null>(null);

const left = computed(() => bytesLeft(text.value));
const ready = computed(() => canSendAll(props.connected, props.to, "", text.value));
const sendLabel = computed(() => (props.to.length > 1 ? t("messages.send_to", { n: props.to.length }) : t("messages.send")));

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
  <ComposeBar
    class="compose"
    :label="t('messages.compose')"
    inline
    :left="left"
    :left-title="leftTitle(left, 'bytes', LIMITS.message.textMax)"
    @submit="submit"
  >
    <label class="sr-only" for="msg-text">{{ t("messages.compose") }}</label>
    <input id="msg-text" ref="input" v-model="text" class="input compose-text" type="text" :placeholder="t('messages.compose')" autocomplete="off" />
    <template #buttons>
      <button type="submit" class="btn primary" :disabled="!ready" :title="sendBlockedReason(connected)">{{ sendLabel }}</button>
    </template>
  </ComposeBar>
</template>
