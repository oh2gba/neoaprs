<script setup lang="ts">
// The box to post to the message board, at the bottom of the Bulletins tab (ComposeBar, as everywhere): the kind (a bulletin, an announcement, a bulletin to a group) with an (i) that says what they are, the number it has (a capital letter for an announcement), the group
// of a group bulletin, and the text, with the characters it has left. Post is on when the text can be sent (printable ASCII without | ~ {) and, for a group, the group is one to five letters and digits. The text is
// cleared when the daemon has the bulletin (the topic `own_bulletins` tells it); one it refused stays for the user to correct. A slot that already holds a text of ours gets the new one in its place.
import { computed, reactive, ref, watch } from "vue";
import ComposeBar from "@/components/ComposeBar.vue";
import InfoTip from "@/components/InfoTip.vue";
import { leftTitle } from "@/lib/compose";
import { LIMITS } from "@/protocol/lists";
import type { OwnBulletinRow } from "@/protocol/protocol";
import { GROUP_MAX, POST_KINDS, canPost, charsLeft, groupOf, groupOk, idsOf, postCommand, type PostDraft } from "@/lib/bulletins";

const props = defineProps<{ ownBulletins: ReadonlyMap<string, OwnBulletinRow> }>();
const emit = defineEmits<{ post: [slot: string, text: string] }>();
const draft = reactive<PostDraft>({ kind: "bulletin", id: "1", group: "", text: "" });

const left = computed(() => charsLeft(draft.text));
const ready = computed(() => canPost(draft));
const badGroup = computed(() => draft.group.trim() !== "" && !groupOk(draft.group));

watch(
  () => draft.kind,
  (kind) => {
    if (!idsOf(kind).includes(draft.id)) draft.id = idsOf(kind).slice(0, 1);
  },
);

const asked = ref<{ slot: string; text: string; before: OwnBulletinRow | undefined } | null>(null); // what was posted, until the daemon has it

watch(
  () => (asked.value === null ? undefined : props.ownBulletins.get(asked.value.slot)),
  (row) => {
    const sent = asked.value;
    if (sent === null || row === undefined || row === sent.before || row.text !== sent.text) return;
    asked.value = null;
    if (draft.text.trim() === sent.text) draft.text = "";
  },
);

function submit(): void {
  const command = postCommand(draft);
  if (command === null) return;
  draft.group = groupOf(draft.group);
  asked.value = { slot: command.slot, text: command.text, before: props.ownBulletins.get(command.slot) };
  emit("post", command.slot, command.text);
}
</script>

<template>
  <ComposeBar
    class="bulletin-compose"
    label="Post a bulletin"
    :left="left"
    :left-title="leftTitle(left, 'characters', LIMITS.message.textMax)"
    @submit="submit"
  >
    <div class="compose-row labelled">
      <div class="stack">
        <label for="post-kind">Kind</label>
        <select id="post-kind" v-model="draft.kind" class="input">
          <option v-for="k in POST_KINDS" :key="k.kind" :value="k.kind">{{ k.title }}</option>
        </select>
      </div>
      <InfoTip label="What the kinds are">
        A bulletin is for everyone and nobody acknowledges it. A bulletin to a group is for the stations that follow that group name. To reach particular
        stations, with an acknowledgement from each, send them a message: Messages tab, Stations.
      </InfoTip>
      <div class="stack">
        <label for="post-id">{{ draft.kind === "announcement" ? "Letter" : "Number" }}</label>
        <select id="post-id" v-model="draft.id" class="input mono">
          <option v-for="c in idsOf(draft.kind)" :key="c" :value="c">{{ c }}</option>
        </select>
      </div>
      <div v-if="draft.kind === 'group'" class="stack">
        <label for="post-group">Group</label>
        <input
          id="post-group"
          v-model="draft.group"
          class="input mono compose-group"
          :class="{ invalid: badGroup }"
          type="text"
          placeholder="Name"
          :maxlength="GROUP_MAX"
          autocomplete="off"
          spellcheck="false"
        />
      </div>
    </div>
    <label class="sr-only" for="post-text">Text</label>
    <input id="post-text" v-model="draft.text" class="input compose-text" type="text" placeholder="Text" autocomplete="off" />
    <template #buttons>
      <button type="submit" class="btn primary" :disabled="!ready">Post</button>
    </template>
  </ComposeBar>
</template>
