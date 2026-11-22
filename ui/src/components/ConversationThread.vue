<script setup lang="ts">
// The messages with one station as bubbles, oldest first, ours at the right: text, time and, for
// ours, the mark, the state with Retry or Cancel and the delivery chain (MessageChain); for
// incoming ones the route and SNR. Encrypted messages carry a padlock; unreadable ones and key
// announcements show what they are. A query we sent (no message id) is a small grey line. `peer`
// is null while a new message is being written. Retry is off while the radio is not connected
// (`offline`). Right-click copies the text (CopyMenu).
import { computed, ref } from "vue";
import CopyMenu from "@/components/CopyMenu.vue";
import IconButton from "@/components/IconButton.vue";
import LockGlyph from "@/components/LockGlyph.vue";
import MessageChain from "@/components/MessageChain.vue";
import MessageMark from "@/components/MessageMark.vue";
import TagMark from "@/components/TagMark.vue";
import { t } from "@/i18n";
import { useCopyMenu } from "@/composables/useCopyMenu";
import { useCameOn } from "@/composables/useStationRadio";
import { radioTone } from "@/lib/channels";
import { useSure } from "@/composables/useSure";
import { useToNewest } from "@/composables/useToNewest";
import { clockText, dateTimeText } from "@/lib/format";
import { markOf as sealMarkOf, shownText } from "@/lib/lock";
import { readingText } from "@/lib/signal";
import { routeWords } from "@/lib/routes";
import { askedNote, canCancel, canDelete, canRetry, stateText } from "@/lib/messages";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ thread: readonly MessageRow[]; peer: string | null; heardDirect?: ReadonlySet<string>; offline?: string }>(), {
  heardDirect: () => new Set<string>(),
  offline: undefined,
});
const emit = defineEmits<{ retry: [id: number]; cancel: [id: number]; delete: [id: number] }>();
const sure = useSure<number>();

const log = ref<HTMLElement | null>(null);
const cameOn = useCameOn();
/** Each message with the note of its query if it is one, its mark (padlock, key) and its radio
 * tag where radios are named. */
const items = computed(() => props.thread.map((m) => ({ m, asked: askedNote(m), seal: sealMarkOf(m), on: cameOn(m) })));

/** What the radio measured of an incoming message ("SNR −3 dB"); null for ours or when it gave
 * none. */
const reading = (m: MessageRow): string | null => (m.direction === "in" ? readingText(m) : null);

useToNewest(log, () => [props.peer, props.thread.length]);
/** The copy menu of a bubble: its message text. */
const copy = useCopyMenu((bubble) => {
  const row = props.thread.find((m) => String(m.id) === bubble.dataset["id"]);
  return row === undefined ? [] : [{ kind: "message", text: row.text }];
});
</script>

<template>
  <div ref="log" class="bubbles" role="log" :aria-label="peer === null ? t('messages.thread') : t('messages.thread_with', { peer })">
    <p v-if="peer !== null && thread.length === 0" class="empty">{{ t("messages.thread_empty", { peer }) }}</p>
    <template v-for="{ m, asked, seal, on } in items" :key="m.id">
      <p v-if="asked" class="asked muted" data-asked>
        <span>{{ asked }}</span>
        <span :title="dateTimeText(m.at)">{{ clockText(m.at) }}</span>
        <MessageMark v-if="m.state === 'sending'" :row="m" />
      </p>
      <div
        v-else
        class="bubble copysource"
        tabindex="0"
        :class="[m.direction === 'in' ? 'in' : 'out', { queued: m.state === 'queued' }]"
        :data-direction="m.direction"
        :data-id="m.id"
        v-on="copy.on.value"
      >
        <p class="bubble-text" :class="{ sealed: m.seal !== '' && m.seal !== 'open' }">{{ shownText(m) }}</p>
        <p class="bubble-meta muted">
          <span :title="dateTimeText(m.at)">{{ clockText(m.at) }}</span>
          <LockGlyph v-if="seal" :kind="seal.kind" :title="seal.title" />
          <MessageMark :row="m" />
          <span v-if="m.direction === 'out'" class="msg-state" :class="`state-${m.state}`">{{ stateText(m) }}</span>
          <button v-if="canRetry(m)" type="button" class="btn small" :disabled="offline !== undefined" :title="offline" @click="emit('retry', m.id)">
            {{ t("messages.retry") }}
          </button>
          <button v-if="canCancel(m)" type="button" class="btn small" @click="emit('cancel', m.id)">{{ t("messages.cancel") }}</button>
          <IconButton
            v-if="canDelete(m)"
            kind="delete"
            class="bubble-delete"
            :armed="sure.armed.value === m.id"
            :label="t('messages.delete')"
            :title="t('messages.delete')"
            @click="sure.press(m.id, () => emit('delete', m.id))"
          />
        </p>
        <MessageChain v-if="m.direction === 'out'" :row="m" :heard-direct="heardDirect" />
        <p v-if="m.route || on || reading(m) !== null" class="bubble-route muted" :title="t('messages.route_title')">
          <TagMark v-if="on" :tone="radioTone(on)" :title="t('radio.heard_on', { name: on.name })">{{ on.name }}</TagMark> {{ routeWords(m.route)
          }}<template v-if="reading(m) !== null"><template v-if="m.route || on"> · </template>{{ reading(m) }}</template>
        </p>
      </div>
    </template>
    <CopyMenu v-if="copy.menu.value" :key="copy.key.value" v-bind="copy.menu.value" @close="copy.close()" />
  </div>
</template>
