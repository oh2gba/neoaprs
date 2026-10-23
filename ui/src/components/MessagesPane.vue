<script setup lang="ts">
// The Messages tab: the conversations (one for each other station, the newest first, with the number of messages not seen yet; a click on the row of the one that is open closes its thread, a click on another opens that one, and the delete button at the right
// end of a row deletes the whole conversation, or the whole overheard pair, after "sure?": the one way to delete, a single message has no button), the thread of the open one (MessageThread) and the box to write in (MessageCompose, which can also write one text to several stations). A conversation with messages
// not seen that is not the open one is highlighted. Under the list is "Route", closed unless the route of the open conversation was changed: the path the station's messages go by (with the suggested one) and the tickbox RF only. A message that came in has the route it came by under its time ("via OH2RCH-2"). "Show overheard" lists the messages sent to other stations, a pair of stations at a time, which are otherwise left out.
import Disclosure from "@/components/Disclosure.vue";
import IconButton from "@/components/IconButton.vue";
import InfoTip from "@/components/InfoTip.vue";
import MessageCompose from "@/components/MessageCompose.vue";
import MessageThread from "@/components/MessageThread.vue";
import StationPrefs from "@/components/StationPrefs.vue";
import { useSure } from "@/composables/useSure";
import { ageText } from "@/lib/format";
import { conversationName, effectivePath, isHighlighted, isOverheard, overheardPair, type Conversation } from "@/lib/messages";
import { unreadText } from "@/lib/unread";
import type { Candidate } from "@/lib/recipients";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{
    conversations: readonly Conversation[];
    selected: string | null;
    thread: readonly MessageRow[];
    connected: boolean;
    now: number;
    showOverheard: boolean;
    paths: ReadonlyMap<string, string>;
    /** the path to send by that the daemon suggests for each station that has one (see the station card) */
    suggestions?: ReadonlyMap<string, string | null>;
    /** the path of the setting beacon/path, which a station without one of its own has */
    fallbackPath: string;
    /** the stations that are RF only */
    rfOnly?: ReadonlySet<string>;
    /** the stations heard direct, which the chain under a message judges a digipeater that was not heard by */
    heardDirect?: ReadonlySet<string>;
    /** the stations that can be picked in the compose box's list "Stations" (lib/recipients.ts) */
    candidates?: readonly Candidate[];
  }>(),
  { rfOnly: () => new Set<string>(), suggestions: () => new Map<string, string | null>(), heardDirect: () => new Set<string>(), candidates: () => [] },
);
const emit = defineEmits<{
  /** a conversation was picked; null when the one that is open was picked again, which closes it */
  select: [call: string | null];
  send: [to: string, text: string];
  /** one text to several stations: a message of its own for each */
  sendMany: [to: string[], text: string];
  retry: [id: number];
  cancel: [id: number];
  deleteConversation: [call: string];
  /** every overheard message of the pair: who sent it, who it was for */
  deleteOverheard: [from: string, to: string];
  "update:showOverheard": [show: boolean];
  path: [call: string, path: string];
  clearPath: [call: string];
  setRfOnly: [call: string, on: boolean];
}>();

const sure = useSure<string>(); // (the call of a conversation, the pair of an overheard one)

/** Whether the route of the open conversation is not the default one (a path of its own, or RF only): the Route is then shown open. */
function routeChanged(call: string): boolean {
  return effectivePath(props.paths, props.fallbackPath, call).own || props.rfOnly.has(call);
}

/** The delete of a row: the conversation goes, or the overheard pair. */
function remove(call: string): void {
  const pair = overheardPair(call);
  if (pair === null) emit("deleteConversation", call);
  else emit("deleteOverheard", pair[0], pair[1]);
}
</script>

<template>
  <div class="msgpane" :class="{ 'has-thread': selected !== null }">
    <div class="toolbar">
      <label class="check"
        ><input type="checkbox" :checked="showOverheard" @change="emit('update:showOverheard', ($event.target as HTMLInputElement).checked)" /> Show
        overheard</label
      >
      <InfoTip label="What overheard means">Messages that other stations sent to each other and that we heard on the radio.</InfoTip>
    </div>
    <ul class="convs" :class="{ short: selected !== null }" aria-label="Conversations">
      <li v-for="c in conversations" :key="c.call" class="conv-item" :class="{ open: c.call === selected }">
        <button
          type="button"
          class="conv"
          :class="{ active: c.call === selected, unread: c.unread > 0, fresh: isHighlighted(c.unread, c.call, selected) }"
          :aria-current="c.call === selected"
          @click="emit('select', c.call === selected ? null : c.call)"
        >
          <span class="conv-call">{{ conversationName(c.call) }}</span>
          <span v-if="c.unread > 0" class="badge" :title="unreadText(c.unread)">{{ c.unread }}</span>
          <span class="conv-age muted">{{ ageText(c.last.at, now) }}</span>
          <span class="conv-text muted">{{ c.last.direction === "out" ? "You: " : "" }}{{ c.last.text }}</span>
        </button>
        <IconButton
          kind="delete"
          class="conv-delete"
          :armed="sure.armed.value === c.call"
          :label="c.overheard ? `Delete the overheard messages ${conversationName(c.call)}` : `Delete the conversation with ${c.call}`"
          @click="sure.press(c.call, () => remove(c.call))"
        />
      </li>
      <li v-if="conversations.length === 0" class="empty">No message yet.</li>
    </ul>
    <div v-if="selected !== null" class="thread-head">
      <p v-if="isOverheard(selected)" class="muted">Overheard: {{ conversationName(selected) }}</p>
      <Disclosure v-else :key="selected" title="Route" :open="routeChanged(selected)">
        <StationPrefs
          :call="selected"
          :paths="paths"
          :fallback-path="fallbackPath"
          :rf-only="rfOnly"
          :suggested="suggestions.get(selected) ?? null"
          @path="(c, p) => emit('path', c, p)"
          @clear-path="emit('clearPath', $event)"
          @set-rf-only="(c, on) => emit('setRfOnly', c, on)"
        />
      </Disclosure>
    </div>
    <MessageThread :thread="thread" :peer="selected" :heard-direct="heardDirect" @retry="emit('retry', $event)" @cancel="emit('cancel', $event)" />
    <MessageCompose
      :selected="selected"
      :connected="connected"
      :candidates="candidates"
      @send="(to, text) => emit('send', to, text)"
      @send-many="(to, text) => emit('sendMany', to, text)"
    />
  </div>
</template>
