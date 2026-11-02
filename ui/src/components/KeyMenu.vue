<script setup lang="ts">
// "Key" in the header of a conversation, beside Route, while encrypted messages are on: a button of the same make that opens a box under the header with the station's key (its fingerprint and when it was heard, or that it has not sent one),
// Send my key (our public key goes to the station as an ordinary message) and, when the station's key is here, Forget key (pressed twice: the next key it announces is then taken). Closed by Esc, a click outside or the focus moving away, as Route is.
// A dot on the button says the station's key is here.
import { ref, watch } from "vue";
import TwoWords from "@/components/TwoWords.vue";
import { t } from "@/i18n";
import { usePopup } from "@/composables/usePopup";
import { useSure } from "@/composables/useSure";
import { dateTimeText } from "@/lib/format";
import type { StationKey } from "@/protocol/protocol";

defineProps<{ call: string; theirs: StationKey | null }>();
const emit = defineEmits<{ sendKey: [call: string]; forget: [call: string] }>();

const open = ref(false);
const root = ref<HTMLElement | null>(null);
const button = ref<HTMLButtonElement | null>(null);
const sure = useSure<string>();
const popup = usePopup({ open, root, trigger: button, close: () => (open.value = false), stopEscape: true });
watch(
  () => open.value,
  () => sure.disarm(),
);
</script>

<template>
  <div ref="root" class="routemenu keymenu" @keydown="popup.onEscape">
    <button
      ref="button"
      type="button"
      class="btn route-button"
      :class="{ changed: theirs !== null }"
      :aria-expanded="open"
      :title="t('lock.button_title', { call })"
      @click="open = !open"
    >
      {{ t("lock.button") }}<span v-if="theirs !== null" class="route-dot" aria-hidden="true"></span>
    </button>
    <div v-if="open" class="route-box keybox">
      <p v-if="theirs === null" class="muted keybox-line">{{ t("lock.none", { call }) }}</p>
      <p v-else class="keybox-line">
        <span class="mono">{{ theirs.fingerprint }}</span>
        <span class="muted">{{ t("lock.heard", { date: dateTimeText(theirs.heard_at) }) }}</span>
      </p>
      <p class="keybox-buttons">
        <button type="button" class="btn" @click="emit('sendKey', call)">{{ t("lock.send_key") }}</button>
        <button
          v-if="theirs !== null"
          type="button"
          class="btn"
          :class="{ danger: sure.armed.value === call }"
          @click="sure.press(call, () => emit('forget', call))"
        >
          <TwoWords :second="sure.armed.value === call">
            <template #first>{{ t("lock.forget") }}</template>
            <template #second>{{ t("lock.forget_sure") }}</template>
          </TwoWords>
        </button>
      </p>
    </div>
  </div>
</template>
