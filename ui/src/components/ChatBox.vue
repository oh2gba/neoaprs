<script setup lang="ts">
// The chat at the bottom of the HF tests tab (useChat, held by the shell): the lines oldest to
// newest in a list of its own height, each with its time, call and text (always as text), and the
// line to write with Send (ComposeBar inline: Enter sends, an IME's Enter is its own). The list
// follows the newest line while the reader is at its end, and stays where the reader scrolled while
// he reads older ones; nothing but the list's own content grows. The one quiet line above the input
// is kept, empty or not, so that a closed chat moves nothing. Without a call the line is off, as Post
// of the tests is.
import { computed, nextTick, onMounted, ref, watch } from "vue";
import ComposeBar from "@/components/ComposeBar.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useSocketOpen } from "@/composables/useInFlight";
import { t } from "@/i18n";
import { chatText } from "@/lib/chat";
import { leftTitle } from "@/lib/compose";
import { dateTimeText, hourMinuteText } from "@/lib/format";
import { mayPostAs } from "@/lib/skeds";
import { characters, leftOf, type TextLimit, typedInto } from "@/lib/textlimit";
import { LIMITS } from "@/protocol/lists";

const { chat, call } = useDaemonContext();
const socketOpen = useSocketOpen();
const list = ref<HTMLElement | null>(null);
const limit: TextLimit = { max: LIMITS.chat.textMax, measure: characters, kind: "characters" };
const left = computed(() => leftOf(chat.draft.value, limit));
const state = computed(() => chat.state.value);
const usable = computed(() => mayPostAs(call.value) && state.value !== "off" && state.value !== "closed");
const ready = computed(
  () => usable.value && socketOpen.value && !chat.busy.value && chatText(chat.draft.value) !== "" && left.value >= 0,
);

/** Whether the list shows its end, within a pixel or two of rounding. */
const atEnd = (box: HTMLElement): boolean => box.scrollHeight - box.scrollTop - box.clientHeight < 4;
const toEnd = (): void => {
  if (list.value) list.value.scrollTop = list.value.scrollHeight;
};
let following = true;
const onScroll = (): void => {
  if (list.value) following = atEnd(list.value);
};
watch(
  () => chat.lines.value.length > 0 && chat.lines.value[chat.lines.value.length - 1]?.id,
  () => {
    const keep = following;
    void nextTick(() => keep && toEnd());
  },
);
onMounted(toEnd);

function submit(): void {
  if (ready.value) chat.say();
}
</script>

<template>
  <fieldset class="board-section chat" :aria-label="t('skeds.chat_title')">
    <legend class="board-title">{{ t("skeds.chat_title") }}</legend>
    <ol ref="list" class="chat-lines" tabindex="0" :aria-label="t('skeds.chat_title')" @scroll="onScroll">
      <li v-if="chat.lines.value.length === 0 && (state === 'ok' || state === 'closed')" class="empty">
        {{ t("skeds.chat_empty") }}
      </li>
      <li v-for="line in chat.lines.value" :key="line.id" class="chat-line" :class="{ ours: line.ours }">
        <time class="chat-at mono" :datetime="line.at" :title="dateTimeText(line.at)">{{
          hourMinuteText(line.at)
        }}</time>
        <span class="chat-call">{{ line.call }}</span>
        <span class="chat-text">{{ line.text }}</span>
      </li>
    </ol>
    <p class="chat-state muted">{{ state === "closed" ? t("skeds.chat_closed") : "" }}</p>
    <ComposeBar
      class="chat-compose"
      :label="t('skeds.chat_label')"
      inline
      :left="left"
      :left-max="LIMITS.chat.textMax"
      :left-title="leftTitle(left, 'characters', LIMITS.chat.textMax)"
      @submit="submit"
    >
      <label class="sr-only" for="chat-text">{{ t("skeds.chat_label") }}</label>
      <input
        id="chat-text"
        :value="chat.draft.value"
        class="input compose-text"
        type="text"
        autocomplete="off"
        :disabled="!usable"
        @input="chat.draft.value = typedInto($event, chat.draft.value, limit)"
        @compositionend="chat.draft.value = typedInto($event, chat.draft.value, limit)"
      />
      <template #buttons>
        <button type="submit" class="btn primary" :disabled="!ready">{{ t("skeds.chat_send") }}</button>
      </template>
    </ComposeBar>
  </fieldset>
</template>
