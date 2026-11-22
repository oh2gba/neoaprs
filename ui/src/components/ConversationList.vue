<script setup lang="ts">
// The Messages tab's conversation list, newest first: call (or overheard pair), age, last text
// and unseen count. The trash button deletes the whole conversation after "sure?"; a single
// message has no button. Right-click copies the call (CopyMenu).
import TagMark from "@/components/TagMark.vue";
import CopyMenu from "@/components/CopyMenu.vue";
import IconButton from "@/components/IconButton.vue";
import InfoTip from "@/components/InfoTip.vue";
import TabHelp from "@/components/TabHelp.vue";
import { t } from "@/i18n";
import { useCopyMenu } from "@/composables/useCopyMenu";
import { useSure } from "@/composables/useSure";
import { ageText } from "@/lib/format";
import { shownText } from "@/lib/lock";
import { askedNote, conversationName, isHighlighted, overheardPair, type Conversation } from "@/lib/messages";
import { unreadText } from "@/lib/unread";

defineProps<{ conversations: readonly Conversation[]; selected: string | null; now: number; showOverheard: boolean }>();
const emit = defineEmits<{
  select: [call: string];
  "update:showOverheard": [show: boolean];
  deleteConversation: [call: string];
  /** every overheard message of the pair: who sent it, who it was for */
  deleteOverheard: [from: string, to: string];
}>();

const sure = useSure<string>();
/** The copy menu of a row: its call, or both calls of an overheard pair. */
const copy = useCopyMenu((row) => {
  const call = row.dataset["call"];
  if (call === undefined) return [];
  return (overheardPair(call) ?? [call]).map((text) => ({ kind: "call" as const, text }));
});

/** The last text on a row: "You: " before ours, or the note for a query we sent. */
function preview(row: Conversation["last"]): string {
  const asked = askedNote(row);
  if (asked !== null) return asked;
  const text = shownText(row);
  return row.direction === "out" ? t("messages.last_out", { text }) : text;
}

/** The delete of a row: the conversation, or the overheard pair. */
function remove(call: string): void {
  const pair = overheardPair(call);
  if (pair === null) emit("deleteConversation", call);
  else emit("deleteOverheard", pair[0], pair[1]);
}
</script>

<template>
  <section class="convlist" :aria-label="t('messages.conversations')">
    <TabHelp :label="t('messages.about_label')">
      <span class="info-line">{{ t("messages.about1") }}</span>
      <span class="info-line">{{ t("messages.about2") }}</span>
    </TabHelp>
    <div class="convlist-head">
      <div class="convlist-overheard">
        <label class="check"
          ><input type="checkbox" :checked="showOverheard" @change="emit('update:showOverheard', ($event.target as HTMLInputElement).checked)" />
          {{ t("messages.show_overheard") }}</label
        >
        <InfoTip :label="t('messages.overheard_help_label')">{{ t("messages.overheard_help") }}</InfoTip>
      </div>
    </div>
    <ul class="convs">
      <li v-for="c in conversations" :key="c.call" class="conv-item" :class="{ open: c.call === selected }">
        <button
          type="button"
          class="conv copysource"
          :class="{ active: c.call === selected, unread: c.unread > 0, fresh: isHighlighted(c.unread, c.call, selected), heard: c.overheard }"
          :data-call="c.call"
          :aria-current="c.call === selected"
          v-on="copy.on.value"
          @click="copy.unlessHeld(() => emit('select', c.call))"
        >
          <span class="conv-call">{{ conversationName(c.call) }}</span>
          <span class="conv-age muted">{{ ageText(c.last.at, now) }}</span>
          <span class="conv-text muted">{{ preview(c.last) }}</span>
          <TagMark v-if="c.unread > 0" class="badge" :title="unreadText(c.unread)">{{ c.unread }}</TagMark>
        </button>
        <IconButton
          kind="delete"
          class="conv-delete"
          :armed="sure.armed.value === c.call"
          :label="c.overheard ? t('messages.delete_overheard', { name: conversationName(c.call) }) : t('messages.delete_conversation', { call: c.call })"
          @click="sure.press(c.call, () => remove(c.call))"
        />
      </li>
      <li v-if="conversations.length === 0" class="empty">{{ t("messages.none_yet") }}</li>
    </ul>
    <CopyMenu v-if="copy.menu.value" :key="copy.key.value" v-bind="copy.menu.value" @close="copy.close()" />
  </section>
</template>
