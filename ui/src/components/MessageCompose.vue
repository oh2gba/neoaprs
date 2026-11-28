<script setup lang="ts">
// The box to write a message at the bottom of a conversation: the text, the bytes left and Send
// (ComposeBar). There is no To: `to` is the station's call, or for a group (GroupCompose) the
// picked calls, and Send reads "Send to 3". Send is off while the radio is not connected
// (`offline`) or the text is empty or too long (lib/recipients.ts `canSendAll`). One recipient
// emits `send`; several emit `sendMany`. With `lockable` a padlock precedes Send: when pressed
// the message is encrypted, the counter counts the 34 bytes an encrypted message holds and ä and
// ö are allowed. `max` is fewer bytes where the radio's frame leaves no room for more.
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

const props = withDefaults(
  defineProps<{
    to: readonly string[];
    connected: boolean;
    lockable?: boolean;
    offline?: string;
    max?: number | null;
  }>(),
  {
    lockable: false,
    offline: undefined,
    max: null,
  },
);
const emit = defineEmits<{
  send: [to: string, text: string, locked: boolean];
  sendMany: [to: string[], text: string];
}>();

/** The text being written, kept by the page so that a draft survives leaving and re-entering the
 * conversation. */
const text = defineModel<string>("text", { default: "" });
const input = ref<HTMLInputElement | null>(null);

/** The padlock is pressed: the message is encrypted. It releases when the station can no longer
 * be written to that way. */
const locked = ref(false);
const encryption = __ENCRYPTION__;
watch(
  () => props.lockable,
  (can) => {
    if (!can) locked.value = false;
  },
);
/** The bytes a message holds (34 if encrypted); the field takes no more (lib/textlimit.ts). */
const limit = computed<TextLimit>(() => ({
  max: Math.min(locked.value ? LIMITS.message.lockedMax : LIMITS.message.textMax, props.max ?? Infinity),
  measure: bytes,
  kind: "bytes",
}));
const left = computed(() => leftOf(text.value, limit.value));
const rxOnly = useReceiveOnly();
const socketOpen = useSocketOpen();
/** The reason the daemon would refuse a character (an encrypted text may have any); marks the
 * field. */
const refused = computed(() => {
  const problem = locked.value ? null : textRefusal(text.value);
  return problem === null ? "" : errorReason({ cmd: "send_message", key: null, text: "", ...problem });
});
const ready = computed(() =>
  locked.value
    ? props.connected && text.value.trim() !== "" && left.value >= 0
    : canSendAll(props.connected, props.to, "", text.value) && left.value >= 0,
);
const sendLabel = computed(() =>
  props.to.length > 1 ? t("messages.send_to", { n: props.to.length }) : t("messages.send"),
);

defineExpose({ focusText: (): void => input.value?.focus() });

/** The text clears only once it went to the daemon; Send is off while the socket is closed. */
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
        v-if="encryption && lockable"
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
        :title="
          !socketOpen
            ? t('pill.daemon_offline')
            : rxOnly || connected
              ? sendBlockedReason(connected, rxOnly)
              : (offline ?? sendBlockedReason(connected))
        "
      >
        {{ sendLabel }}
      </button>
    </template>
  </ComposeBar>
</template>
