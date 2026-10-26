<script setup lang="ts">
// The group box to post to the message board, at the bottom of the Bulletins tab (ComposeBar, as everywhere; the fields are rows like those of the Objects form, each with its (i)): the kind (a bulletin, an announcement, a bulletin to a group) (the (i) says what they are), the number it has (a capital letter for an announcement), the group
// of a group bulletin, and the text, with the characters it has left. Post is on when the text can be sent (printable ASCII without | ~ {) and, for a group, the group is one to five letters and digits. The text is
// cleared when the daemon has the bulletin (the topic `own_bulletins` tells it); one it refused stays for the user to correct. A slot that already holds a text of ours gets the new one in its place.
import { useReceiveOnly } from "@/composables/useReceiveOnly";
import { rxOnlyReason } from "@/lib/compose";
import { computed, reactive, ref, watch } from "vue";
import ComposeBar from "@/components/ComposeBar.vue";
import InfoTip from "@/components/InfoTip.vue";
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { leftTitle } from "@/lib/compose";
import { LIMITS } from "@/protocol/lists";
import type { OwnBulletinRow } from "@/protocol/protocol";
import { GROUP_MAX, POST_KINDS, canPost, charsLeft, groupOf, groupOk, idsOf, kindTitle, postCommand, type PostDraft } from "@/lib/bulletins";

const props = defineProps<{ ownBulletins: ReadonlyMap<string, OwnBulletinRow> }>();
const emit = defineEmits<{ post: [slot: string, text: string] }>();
const draft = reactive<PostDraft>({ kind: "bulletin", id: "1", group: "", text: "" });

const left = computed(() => charsLeft(draft.text));
/** The name of an (i) for a screen reader: "About Group". */
const about = (field: MessageId) => t("settings.about", { label: t(field) });
const rxOnly = useReceiveOnly();
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
    :label="t('bulletins.post_label')"
    :left="left"
    :left-title="leftTitle(left, 'characters', LIMITS.message.textMax)"
    @submit="submit"
  >
    <div class="field">
      <label for="post-kind">{{ t("bulletins.kind") }}</label>
      <div class="field-control">
        <select id="post-kind" v-model="draft.kind" class="input">
          <option v-for="k in POST_KINDS" :key="k.kind" :value="k.kind">{{ kindTitle(k.kind) }}</option>
        </select>
        <InfoTip :label="t('bulletins.kinds_help_label')">{{ t("bulletins.kinds_help") }}</InfoTip>
      </div>
    </div>
    <div class="field">
      <label for="post-id">{{ t(draft.kind === "announcement" ? "bulletins.letter" : "bulletins.number") }}</label>
      <div class="field-control">
        <select id="post-id" v-model="draft.id" class="input mono">
          <option v-for="c in idsOf(draft.kind)" :key="c" :value="c">{{ c }}</option>
        </select>
        <InfoTip :label="about(draft.kind === 'announcement' ? 'bulletins.letter' : 'bulletins.number')">{{ t("bulletins.slot_tip") }}</InfoTip>
      </div>
    </div>
    <div v-if="draft.kind === 'group'" class="field" :class="{ invalid: badGroup }">
      <label for="post-group">{{ t("bulletins.group") }}</label>
      <div class="field-control">
        <input
          id="post-group"
          v-model="draft.group"
          class="input mono"
          :class="{ invalid: badGroup }"
          type="text"
          :placeholder="t('bulletins.group_placeholder')"
          :maxlength="GROUP_MAX"
          autocomplete="off"
          spellcheck="false"
        />
        <InfoTip :label="about('bulletins.group')">{{ t("bulletins.group_tip", { max: GROUP_MAX }) }}</InfoTip>
      </div>
    </div>
    <div class="field">
      <label for="post-text">{{ t("bulletins.text") }}</label>
      <div class="field-control">
        <input id="post-text" v-model="draft.text" class="input" type="text" autocomplete="off" />
        <InfoTip :label="about('bulletins.text')">{{ t("bulletins.text_tip") }}</InfoTip>
      </div>
    </div>
    <template #buttons>
      <button type="submit" class="btn primary" :disabled="!ready || rxOnly" :title="rxOnly ? rxOnlyReason() : undefined">{{ t("bulletins.post") }}</button>
    </template>
  </ComposeBar>
</template>
