<script setup lang="ts">
// The Messages tab's conversation list, newest first: call (or overheard pair), age, last text
// and unseen count. The trash button deletes the whole conversation after "sure?"; a single
// message has no button. Right-click copies the call (CopyMenu). The head has Show overheard, the
// + that opens a conversation with a call typed (one no radio heard too; Write is on while the
// call is one the daemon takes and not ours), and Services (MessageServices).
import { nextTick, ref } from "vue";
import TagMark from "@/components/TagMark.vue";
import CopyMenu from "@/components/CopyMenu.vue";
import IconButton from "@/components/IconButton.vue";
import InfoTip from "@/components/InfoTip.vue";
import MessageServices from "@/components/MessageServices.vue";
import TabHelp from "@/components/TabHelp.vue";
import { t } from "@/i18n";
import { useCopyMenu } from "@/composables/useCopyMenu";
import { useSure } from "@/composables/useSure";
import { boardKind } from "@/lib/bulletins";
import { normalizeCall, validName } from "@/lib/calls";
import { isAlias } from "@/lib/chain";
import { ageText } from "@/lib/format";
import { shownText } from "@/lib/lock";
import { askedNote, conversationName, isHighlighted, overheardPair, type Conversation } from "@/lib/messages";
import { unreadText } from "@/lib/unread";

const props = withDefaults(
  defineProps<{
    conversations: readonly Conversation[];
    selected: string | null;
    now: number;
    showOverheard: boolean;
    /** our own call, which no conversation is with */
    ours?: string | null;
  }>(),
  { ours: null },
);
const emit = defineEmits<{
  select: [call: string];
  "update:showOverheard": [show: boolean];
  deleteConversation: [call: string];
  /** every overheard message of the pair: who sent it, who it was for */
  deleteOverheard: [from: string, to: string];
  /** a ready-made message to a service (MessageServices): its addressee and the start of its text */
  write: [to: string, text: string];
}>();

const sure = useSure<string>();

/** The + was pressed: the call field shows until a conversation is opened, + again or Esc. */
const adding = ref(false);
const typed = ref("");
const field = ref<HTMLInputElement | null>(null);
/** Whether the typed call is one a message may go to: a station's name, not our own call, not a
 * name of the board (BLN1, QST) or of a path (WIDE1-1). */
function writable(text: string): boolean {
  const call = normalizeCall(text);
  return validName(call) && call !== normalizeCall(props.ours ?? "") && boardKind(call) === null && !isAlias(call);
}
async function toggleAdding(): Promise<void> {
  adding.value = !adding.value;
  typed.value = "";
  await nextTick();
  field.value?.focus();
}
function openTyped(): void {
  if (!writable(typed.value)) return;
  emit("write", normalizeCall(typed.value), "");
  adding.value = false;
  typed.value = "";
}
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
          ><input
            type="checkbox"
            :checked="showOverheard"
            @change="emit('update:showOverheard', ($event.target as HTMLInputElement).checked)"
          />
          {{ t("messages.show_overheard") }}</label
        >
        <InfoTip :label="t('messages.overheard_help_label')">{{ t("messages.overheard_help") }}</InfoTip>
        <IconButton kind="add" class="convlist-add" :label="t('messages.new_label')" @click="toggleAdding" />
      </div>
      <div class="convlist-slot">
        <form
          v-if="adding"
          class="convlist-services convlist-new"
          @submit.prevent="openTyped"
          @keydown.esc.stop="adding = false"
        >
          <label for="msg-new-call">{{ t("messages.new_call") }}</label>
          <input
            id="msg-new-call"
            ref="field"
            v-model="typed"
            class="input"
            :class="{ invalid: typed.trim() !== '' && !writable(typed) }"
            :aria-invalid="typed.trim() !== '' && !writable(typed)"
            type="text"
            autocomplete="off"
            spellcheck="false"
          />
          <button type="submit" class="btn" :disabled="!writable(typed)">{{ t("messages.service_write") }}</button>
        </form>
        <MessageServices
          :class="{ held: adding }"
          :inert="adding || undefined"
          @write="(to, text) => emit('write', to, text)"
        />
      </div>
    </div>
    <ul class="convs">
      <li v-for="c in conversations" :key="c.call" class="conv-item" :class="{ open: c.call === selected }">
        <button
          type="button"
          class="conv copysource"
          :class="{
            active: c.call === selected,
            unread: c.unread > 0,
            fresh: isHighlighted(c.unread, c.call, selected),
            heard: c.overheard,
          }"
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
          :label="
            c.overheard
              ? t('messages.delete_overheard', { name: conversationName(c.call) })
              : t('messages.delete_conversation', { call: c.call })
          "
          @click="sure.press(c.call, () => remove(c.call))"
        />
      </li>
      <li v-if="conversations.length === 0" class="empty">{{ t("messages.none_yet") }}</li>
    </ul>
    <CopyMenu v-if="copy.menu.value" :key="copy.key.value" v-bind="copy.menu.value" @close="copy.close()" />
  </section>
</template>
