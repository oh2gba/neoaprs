<script setup lang="ts">
// One conversation of the Messages tab, filling its column: a header bar (on a narrow page the back arrow "‹" to the list; the call; "Route" for the path and RF only; "Key" for the station's key while encrypted messages are on, KeyMenu), the bubbles (ConversationThread) filling the height and the box to write in (MessageCompose: the text,
// "12 left" and Send, no To: the conversation is the station) fixed at the bottom. An overheard pair has no Route and no box to write in (the messages are not ours: only the bubbles, and the delete in the list). It is the page's to put a new one in place of this when
// another conversation is picked (a `key`), and on a narrow page it takes the focus when it appears, so that Esc goes back. The header is not text to select; a right-click on the call offers to copy it (CopyMenu).
import { computed, onMounted, ref } from "vue";
import ConversationThread from "@/components/ConversationThread.vue";
import CopyMenu from "@/components/CopyMenu.vue";
import InfoTip from "@/components/InfoTip.vue";
import KeyMenu from "@/components/KeyMenu.vue";
import MessageCompose from "@/components/MessageCompose.vue";
import RouteMenu from "@/components/RouteMenu.vue";
import TagMark from "@/components/TagMark.vue";
import { t } from "@/i18n";
import { useCopyMenu } from "@/composables/useCopyMenu";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { conversationName, isOverheard, overheardPair, replyTo } from "@/lib/messages";
import { fmOn, hasPaths, hfOn, radioFor, type RadioKind } from "@/lib/radiosides";
import type { MessageRow } from "@/protocol/protocol";

const props = defineProps<{
  selected: string;
  /** one column at a time: the header has the way back to the list */
  narrow: boolean;
  thread: readonly MessageRow[];
}>();
const text = defineModel<string>("text", { default: "" });
const emit = defineEmits<{
  back: [];
  send: [to: string, text: string, locked: boolean];
  retry: [id: number];
  cancel: [id: number];
  delete: [id: number];
}>();
const { connectedOn, heardDirect, heardPaths, fallbackPath, prefs, keys, config, stations, send } = useDaemonContext();
/** The station's row; null for a call nothing is known of. */
const row = computed(() => stations.value.get(props.selected) ?? null);
/** The radio the messages go over, for FM and HF before Send: only while both radios are on and the station is known (the daemon keeps the choice with the station); "" otherwise. */
const radio = computed<RadioKind | "">(() => {
  const values = config.value?.values ?? {};
  return fmOn(values) && hfOn(values) && row.value !== null ? radioFor(row.value, values) : "";
});
/** The operator chose the other radio for the messages to this station. */
function chooseRadio(kind: RadioKind): void {
  send({ cmd: "message_radio", call: props.selected, radio: kind });
}
/** Its position says it takes no messages and it never sent one: a message may not be read there (it can be sent all the same). */
const mayNot = computed(() => row.value?.may_not_message === true);
/** Whether there is a route to set: the FM radio is on and the station is messaged on it (one heard on HF alone is messaged on HF, which has no paths; lib/radiosides.ts). */
const routable = computed(() => hasPaths(config.value?.values ?? {}, stations.value.get(props.selected) ?? null));
/** Whether the messages to the station go over the HF radio (no path, no RF only: the header says it in Route's place with a tag). */
const overHf = computed(() => radioFor(stations.value.get(props.selected) ?? null, config.value?.values ?? {}) === "hf");
/** Whether the link of the radio the messages to the station take is up. */
const connected = computed(() => connectedOn(radioFor(stations.value.get(props.selected) ?? null, config.value?.values ?? {})));
const { paths, rfOnly } = prefs;

const root = ref<HTMLElement | null>(null);
const heard = computed(() => isOverheard(props.selected));
/** The station's key, for the Key menu; and whether a message to it can be locked. */
const theirs = computed(() => keys.of(replyTo(props.selected)));
const lockable = computed(() => keys.canLock(replyTo(props.selected)));
/** The copy menu of the title: the call, or the two calls of an overheard pair. */
const copy = useCopyMenu(() => (overheardPair(props.selected) ?? [props.selected]).map((text) => ({ kind: "call" as const, text })));

onMounted(() => {
  if (props.narrow) root.value?.focus({ preventScroll: true });
});
</script>

<template>
  <section ref="root" class="convo" tabindex="-1" :aria-label="t('messages.conversation_with', { name: conversationName(selected) })">
    <header class="convo-head">
      <button v-if="narrow" type="button" class="convo-back" :aria-label="t('messages.back_label')" :title="t('messages.back')" @click="emit('back')">
        <span aria-hidden="true">‹</span>
      </button>
      <h3 class="convo-title copysource" v-on="copy.on.value">
        <template v-if="heard">{{ t("messages.overheard_title", { name: conversationName(selected) }) }}</template>
        <template v-else>{{ selected }}</template>
      </h3>
      <TagMark v-if="!heard && overHf && !radio" tone="hf" class="convo-radio" :title="t('messages.hf_tag_title')">{{ t("channel.hf") }}</TagMark>
      <RouteMenu
        v-if="!heard && routable"
        :key="selected"
        :call="selected"
        :paths="paths"
        :fallback-path="fallbackPath"
        :rf-only="rfOnly"
        :heard="heardPaths.get(selected) ?? null"
        @path="prefs.setPath"
        @clear-path="prefs.clearPath"
        @set-rf-only="prefs.setRfOnly"
      />
      <KeyMenu
        v-if="!heard && keys.on.value"
        :key="`key-${selected}`"
        :call="replyTo(selected)"
        :theirs="theirs"
        @send-key="keys.sendKey"
        @forget="keys.forget"
      />
    </header>
    <ConversationThread
      :thread="thread"
      :peer="selected"
      :heard-direct="heardDirect"
      @retry="emit('retry', $event)"
      @cancel="emit('cancel', $event)"
      @delete="emit('delete', $event)"
    />
    <p v-if="!heard && mayNot" class="convo-maynot problem" role="note">
      {{ t("messages.may_not_message") }}
      <InfoTip :label="t('messages.may_not_message_label')">{{ t("messages.may_not_message_help") }}</InfoTip>
    </p>
    <MessageCompose
      v-if="!heard"
      v-model:text="text"
      :to="[replyTo(selected)]"
      :connected="connected"
      :lockable="lockable"
      :radio="radio"
      @send="(to, body, locked) => emit('send', to, body, locked)"
      @radio="chooseRadio"
    />
    <CopyMenu v-if="copy.menu.value" :key="copy.key.value" v-bind="copy.menu.value" @close="copy.close()" />
  </section>
</template>
