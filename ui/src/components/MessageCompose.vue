<script setup lang="ts">
// The box to write a message in, fixed at the bottom of a conversation: the text, how many of the bytes a message may have are left ("12 left") and Send, in one line (ComposeBar of one field, as on every tab). There is no To: the conversation is the station (`to` is its call), or for a group (GroupCompose) the
// calls that were picked, and then Send says "Send to 3". Send is off while the TNC is not connected (its title says so) or the text is empty or too long (lib/recipients.ts `canSendAll`). With one recipient it says `send`; with several it says `sendMany`, which the
// page turns into one ordinary message to each. The text is cleared once it is sent. With `lockable` (encrypted messages are on, the station has sent its key and we have ours) a padlock stands before Send: pressed, the message
// is encrypted (`send` says so), the counter counts the 34 bytes an encrypted message holds, and the text may say ä and ö.
import { computed, ref, watch } from "vue";
import ComposeBar from "@/components/ComposeBar.vue";
import IconButton from "@/components/IconButton.vue";
import { t } from "@/i18n";
import { useReceiveOnly } from "@/composables/useReceiveOnly";
import { leftTitle, sendBlockedReason } from "@/lib/compose";
import { bytesLeft, textBytes } from "@/lib/messages";
import { canSendAll } from "@/lib/recipients";
import { LIMITS } from "@/protocol/lists";

const props = withDefaults(defineProps<{ to: readonly string[]; connected: boolean; lockable?: boolean }>(), { lockable: false });
const emit = defineEmits<{ send: [to: string, text: string, locked: boolean]; sendMany: [to: string[], text: string] }>();

/** The text being written: the page's to keep, so that a draft stays when the user goes back to the list and in again. */
const text = defineModel<string>("text", { default: "" });
const input = ref<HTMLInputElement | null>(null);

/** The padlock is pressed: the message is encrypted. It lets go when the station can no longer be written to that way (its key forgotten, the switch off). */
const locked = ref(false);
watch(
  () => props.lockable,
  (can) => {
    if (!can) locked.value = false;
  },
);
const left = computed(() => (locked.value ? LIMITS.message.lockedMax - textBytes(text.value) : bytesLeft(text.value)));
const rxOnly = useReceiveOnly();
const ready = computed(() =>
  locked.value ? props.connected && text.value.trim() !== "" && left.value >= 0 : canSendAll(props.connected, props.to, "", text.value),
);
const sendLabel = computed(() => (props.to.length > 1 ? t("messages.send_to", { n: props.to.length }) : t("messages.send")));

defineExpose({ focusText: (): void => input.value?.focus() });

function submit(): void {
  if (!ready.value || rxOnly.value) return;
  const [only] = props.to;
  if (props.to.length === 1 && only !== undefined) emit("send", only, text.value, locked.value);
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
    :left-title="leftTitle(left, 'bytes', locked ? LIMITS.message.lockedMax : LIMITS.message.textMax)"
    @submit="submit"
  >
    <label class="sr-only" for="msg-text">{{ t("messages.compose") }}</label>
    <input id="msg-text" ref="input" v-model="text" class="input compose-text" type="text" :placeholder="t('messages.compose')" autocomplete="off" />
    <template #buttons>
      <IconButton
        v-if="lockable"
        kind="lock"
        class="compose-lock"
        :pressed="locked"
        :label="t(locked ? 'lock.toggle_on' : 'lock.toggle_off')"
        @click="locked = !locked"
      />
      <button type="submit" class="btn primary" :disabled="!ready || rxOnly" :title="sendBlockedReason(connected, rxOnly)">{{ sendLabel }}</button>
    </template>
  </ComposeBar>
</template>
