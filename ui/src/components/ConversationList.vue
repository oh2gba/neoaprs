<script setup lang="ts">
// The list of conversations of the Messages tab, the one with the newest message first: the call (or the pair of an overheard one), the age, the last text on one line ("You: " before one of ours) and the number of messages not seen. "Show overheard" (with an (i)) is at its top; the open conversation is the filled row, one with something not seen that is not the open one has its call in bold and a bar at its left. A row is a button that opens the conversation; the trash at the right end of it deletes the whole conversation
// (or the overheard pair) after "sure?": the one way to delete, a single message has no button.
import TagMark from "@/components/TagMark.vue";
import IconButton from "@/components/IconButton.vue";
import InfoTip from "@/components/InfoTip.vue";
import TabHelp from "@/components/TabHelp.vue";
import { t } from "@/i18n";
import { useSure } from "@/composables/useSure";
import { ageText } from "@/lib/format";
import { askedText, conversationName, isHighlighted, overheardPair, queryKind, type Conversation } from "@/lib/messages";
import { unreadText } from "@/lib/unread";

defineProps<{ conversations: readonly Conversation[]; selected: string | null; now: number; showOverheard: boolean }>();
const emit = defineEmits<{
  select: [call: string];
  "update:showOverheard": [show: boolean];
  deleteConversation: [call: string];
  /** every overheard message of the pair: who sent it, who it was for */
  deleteOverheard: [from: string, to: string];
}>();

const sure = useSure<string>(); // (the call of a conversation, the pair of an overheard one)

/** The last text on a row: ours has "You: " before it, a query we sent is the note of it ("You asked for its status"). */
function preview(row: Conversation["last"]): string {
  const asked = queryKind(row);
  if (asked !== null) return askedText(asked);
  return row.direction === "out" ? t("messages.last_out", { text: row.text }) : row.text;
}

/** The delete of a row: the conversation goes, or the overheard pair. */
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
          class="conv"
          :class="{ active: c.call === selected, unread: c.unread > 0, fresh: isHighlighted(c.unread, c.call, selected), heard: c.overheard }"
          :data-call="c.call"
          :aria-current="c.call === selected"
          @click="emit('select', c.call)"
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
  </section>
</template>
