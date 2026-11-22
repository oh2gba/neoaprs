<script setup lang="ts">
// The box to write an email, at the bottom of the Email tab (ComposeBar): To (with earlier
// matching addresses listed while focused), the text, and a counter for the characters the
// "address text" line may still have. Send is off while no radio can send, the email radio is
// not connected (`offline`), the address or text is empty or the line cannot be sent, and while
// the page has no connection. After Send the text clears and the address stays.
import { computed, ref } from "vue";
import ComposeBar from "@/components/ComposeBar.vue";
import IconButton from "@/components/IconButton.vue";
import InfoTip from "@/components/InfoTip.vue";
import { t } from "@/i18n";
import { useRadios } from "@/composables/useRadios";
import { useSocketOpen } from "@/composables/useInFlight";
import { useReceiveOnly } from "@/composables/useReceiveOnly";
import { errorReason } from "@/i18n/errortext";
import { leftTitle, sendBlockedReason } from "@/lib/compose";
import { canSendEmail, emailLine } from "@/lib/email";
import { textRefusal } from "@/lib/recipients";
import { bytes, leftOf, type TextLimit, typedInto } from "@/lib/textlimit";
import { LIMITS } from "@/protocol/lists";

const props = withDefaults(defineProps<{ connected: boolean; addresses: readonly string[]; offline?: string }>(), { offline: undefined });
const emit = defineEmits<{ send: [to: string, text: string]; forget: [name: string] }>();

const to = ref("");
const text = ref("");
const textBox = ref<HTMLInputElement | null>(null);
const listed = ref(false);

/** The message length limit: the address, a space and the text (lib/textlimit.ts). */
const limit = computed<TextLimit>(() => ({ max: LIMITS.message.textMax, measure: (body) => bytes(emailLine(to.value, body)), kind: "address" }));
const left = computed(() => leftOf(text.value, limit.value));
const rxOnly = useReceiveOnly();
const radios = useRadios();
/** No radio that can send is on: there is none for email to go on. */
const none = computed(() => radios.email.value === null);
const socketOpen = useSocketOpen();
/** Why Send is off (no connection, RX only, no email radio, link down); undefined if none. */
const blocked = computed(() =>
  !socketOpen.value
    ? t("pill.daemon_offline")
    : rxOnly.value || props.connected
      ? sendBlockedReason(props.connected, rxOnly.value)
      : (props.offline ?? sendBlockedReason(false)),
);
/** The reason the daemon would refuse a character in a field; "" if none. */
const refusedIn = (value: string): string => {
  const problem = textRefusal(value);
  return problem === null ? "" : errorReason({ cmd: "send_message", key: null, text: "", ...problem });
};
const toRefused = computed(() => refusedIn(to.value));
const textRefused = computed(() => refusedIn(text.value));
const ready = computed(() => canSendEmail(props.connected, to.value, text.value));
/** Earlier addresses that match what is typed, other than the one typed in full. */
const suggestions = computed(() => {
  const typed = to.value.trim().toLowerCase();
  return props.addresses.filter((a) => a.toLowerCase() !== typed && a.toLowerCase().includes(typed));
});
const shown = computed(() => listed.value && suggestions.value.length > 0);

function pick(address: string): void {
  to.value = address;
  listed.value = false;
  textBox.value?.focus();
}

function leave(event: FocusEvent): void {
  const into = event.relatedTarget;
  if (!(into instanceof Node) || !(event.currentTarget instanceof Node) || !event.currentTarget.contains(into)) listed.value = false;
}

/** Esc closes the open suggestions, else clears the address and the text. */
function escape(): void {
  if (shown.value) {
    listed.value = false;
    return;
  }
  to.value = "";
  text.value = "";
}

/** The text clears only once it went to the daemon; Send is off while the socket is closed. */
function submit(): void {
  if (!ready.value || rxOnly.value || none.value || !socketOpen.value) return;
  emit("send", to.value.trim(), text.value);
  text.value = "";
  textBox.value?.focus();
}
</script>

<template>
  <ComposeBar
    class="mailform"
    :label="t('email.compose')"
    :left="left"
    :left-max="LIMITS.message.textMax"
    :left-title="leftTitle(left, 'address', LIMITS.message.textMax)"
    @submit="submit"
    @keydown.esc.stop="escape"
  >
    <div class="field">
      <label for="mail-to">{{ t("email.field.to") }}</label>
      <div class="field-control">
        <div class="mail-address" @focusout="leave">
          <input
            id="mail-to"
            v-model="to"
            class="input mono"
            :class="{ invalid: toRefused !== '' }"
            :title="toRefused || undefined"
            type="text"
            :placeholder="t('email.field.address')"
            autocomplete="off"
            spellcheck="false"
            @focus="listed = true"
            @input="listed = true"
          />
          <ul v-if="shown" class="suggestions" :aria-label="t('email.used_before')" @mousedown.prevent>
            <li v-for="a in suggestions" :key="a" class="suggestion">
              <button type="button" class="suggestion-pick mono" @click="pick(a)">{{ a }}</button>
              <IconButton kind="delete" :label="t('email.forget', { address: a })" :title="t('email.forget', { address: a })" @click="emit('forget', a)" />
            </li>
          </ul>
        </div>
        <InfoTip :label="t('settings.about', { label: t('email.field.to') })">{{ t("email.to_tip") }}</InfoTip>
      </div>
    </div>
    <div class="field">
      <label for="mail-text">{{ t("email.field.text") }}</label>
      <div class="field-control">
        <input
          id="mail-text"
          ref="textBox"
          :value="text"
          class="input"
          :class="{ invalid: textRefused !== '' }"
          :title="textRefused || undefined"
          type="text"
          autocomplete="off"
          @input="text = typedInto($event, text, limit)"
          @compositionend="text = typedInto($event, text, limit)"
        />
        <InfoTip :label="t('settings.about', { label: t('email.field.text') })">{{ t("email.text_tip") }}</InfoTip>
      </div>
    </div>
    <template #buttons>
      <button type="submit" class="btn primary" :disabled="!ready || rxOnly || none || !socketOpen" :title="blocked">{{ t("email.send") }}</button>
    </template>
  </ComposeBar>
</template>
