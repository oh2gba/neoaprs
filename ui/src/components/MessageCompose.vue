<script setup lang="ts">
// The box to write a message in, fixed at the bottom of a conversation: the text, how many of the bytes a message may have are left ("12 left") and Send, in one line (ComposeBar of one field, as on every tab). There is no To: the conversation is the station (`to` is its call), or for a group (GroupCompose) the
// calls that were picked, and then Send says "Send to 3". Send is off while the radio is not connected (its title says so: `offline`, the words of the radio the messages go on, else those of before) or the text is empty or too
// long (lib/recipients.ts `canSendAll`). With one recipient it says `send`; with several it says `sendMany`, which the
// page turns into one ordinary message to each. The text is cleared once it is sent, and Send is off while the page has no connection to NeoAPRS; a character a message cannot carry marks the field with the reason. With `lockable` (encrypted messages are on, the station has sent its key and we have ours) a padlock stands before Send: pressed, the message
// is encrypted (`send` says so), the counter counts the 34 bytes an encrypted message holds, and the text may say ä and ö. The radio is chosen in Route, never here.
import { computed, ref, watch } from "vue";
import ComposeBar from "@/components/ComposeBar.vue";
import IconButton from "@/components/IconButton.vue";
import { t } from "@/i18n";
import { useSocketOpen } from "@/composables/useInFlight";
import { useReceiveOnly } from "@/composables/useReceiveOnly";
import { errorReason } from "@/i18n/errortext";
import { leftTitle, sendBlockedReason } from "@/lib/compose";
import { canSendAll, textRefusal } from "@/lib/recipients";
import { bytes, leftOf, type TextLimit, typedInto } from "@/lib/textlimit";
import { LIMITS } from "@/protocol/lists";

const props = withDefaults(defineProps<{ to: readonly string[]; connected: boolean; lockable?: boolean; offline?: string }>(), {
  lockable: false,
  offline: undefined,
});
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
/** The bytes a message holds, 34 when it is encrypted; the field takes no more (lib/textlimit.ts, as every field with a counter). */
const limit = computed<TextLimit>(() => ({ max: locked.value ? LIMITS.message.lockedMax : LIMITS.message.textMax, measure: bytes, kind: "bytes" }));
const left = computed(() => leftOf(text.value, limit.value));
const rxOnly = useReceiveOnly();
const socketOpen = useSocketOpen();
/** A character the daemon would refuse (an encrypted text may have any: it goes sealed); the field is marked with the reason. */
const refused = computed(() => {
  const problem = locked.value ? null : textRefusal(text.value);
  return problem === null ? "" : errorReason({ cmd: "send_message", key: null, text: "", ...problem });
});
const ready = computed(() =>
  locked.value ? props.connected && text.value.trim() !== "" && left.value >= 0 : canSendAll(props.connected, props.to, "", text.value),
);
const sendLabel = computed(() => (props.to.length > 1 ? t("messages.send_to", { n: props.to.length }) : t("messages.send")));

defineExpose({ focusText: (): void => input.value?.focus() });

/** The text is cleared only once it went to the daemon: Send is off while the socket is closed, so a draft is never lost to it. */
function submit(): void {
  if (!ready.value || rxOnly.value || !socketOpen.value) return;
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
    :left-max="LIMITS.message.textMax"
    :left-title="leftTitle(left, 'bytes', limit.max)"
    @submit="submit"
  >
    <label class="sr-only" for="msg-text">{{ t("messages.compose") }}</label>
    <input
      id="msg-text"
      ref="input"
      :value="text"
      class="input compose-text"
      :class="{ invalid: refused !== '' }"
      :title="refused || undefined"
      type="text"
      :placeholder="t('messages.compose')"
      autocomplete="off"
      @input="text = typedInto($event, text, limit)"
      @compositionend="text = typedInto($event, text, limit)"
    />
    <template #buttons>
      <IconButton
        v-if="lockable"
        kind="lock"
        class="compose-lock"
        :pressed="locked"
        :label="t(locked ? 'lock.toggle_on' : 'lock.toggle_off')"
        @click="locked = !locked"
      />
      <button
        type="submit"
        class="btn primary"
        :disabled="!ready || rxOnly || !socketOpen"
        :title="!socketOpen ? t('pill.daemon_offline') : rxOnly || connected ? sendBlockedReason(connected, rxOnly) : (offline ?? sendBlockedReason(connected))"
      >
        {{ sendLabel }}
      </button>
    </template>
  </ComposeBar>
</template>
