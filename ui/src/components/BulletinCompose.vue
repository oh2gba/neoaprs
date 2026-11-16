<script setup lang="ts">
// The group box to post to the message board, at the bottom of the Bulletins tab (ComposeBar, as everywhere; the fields are rows like those of the Objects form). No field has an (i): each says what it is by itself.
// The kind is a choice whose options say what each does (a bulletin and an announcement differ in how long they are repeated, a group bulletin in whom it is for: lib/bulletins.ts `kindTitle`, with the daemon's own
// numbers); under it the number the post has (a capital letter for an announcement, the same row), the group of a group bulletin (its row is always there, greyed for the other kinds, so that choosing a kind moves
// nothing) and the text, with the characters it has left. Post is on when the text can be sent (printable ASCII without | ~ {) and, for a group, the group is one to five letters and digits; it says Replace while the
// number, letter or group chosen holds a post of ours, which the new text replaces (both words are in the button, TwoWords: it is as wide as the longer). The text is
// cleared when the daemon has the bulletin (the topic `own_bulletins` tells it); one it refused stays for the user to correct. A bulletin goes on the main radio
// (plan rule 3.5): Post is off while that radio is not connected, with that as its reason (the radio named while several are on), as Send is.
import { useRadios } from "@/composables/useRadios";
import { useReceiveOnly } from "@/composables/useReceiveOnly";
import { radioBlockedReason, rxOnlyReason } from "@/lib/compose";
import { computed, reactive, ref, watch } from "vue";
import ComposeBar from "@/components/ComposeBar.vue";
import TwoWords from "@/components/TwoWords.vue";
import { t } from "@/i18n";
import { leftTitle } from "@/lib/compose";
import { LIMITS } from "@/protocol/lists";
import type { OwnBulletinRow } from "@/protocol/protocol";
import { leftOf, type TextLimit, trimmedCharacters, typedInto } from "@/lib/textlimit";
import { GROUP_MAX, POST_KINDS, canPost, groupOf, groupOk, idsOf, kindTitle, postCommand, slotOf, type PostDraft } from "@/lib/bulletins";

const props = defineProps<{ ownBulletins: ReadonlyMap<string, OwnBulletinRow> }>();
const emit = defineEmits<{ post: [slot: string, text: string] }>();
const draft = reactive<PostDraft>({ kind: "bulletin", id: "1", group: "", text: "" });

/** The characters of a message; the field takes no more (lib/textlimit.ts, as every field with a counter). */
const limit: TextLimit = { max: LIMITS.message.textMax, measure: trimmedCharacters, kind: "characters" };
const left = computed(() => leftOf(draft.text, limit));
const rxOnly = useReceiveOnly();
const { told, main, named } = useRadios();
/** Why nothing may go on the main radio: it is not connected, or there is none; undefined before the daemon has told its radios. */
const offline = computed(() => radioBlockedReason(main.value, main.value !== null && named(main.value.id), told.value));
const ready = computed(() => canPost(draft));
const grouped = computed(() => draft.kind === "group");
const badGroup = computed(() => grouped.value && draft.group.trim() !== "" && !groupOk(draft.group));
/** Whether the number, letter or number and group chosen holds a post of ours: the new text takes its place. A group bulletin without its group is for no place yet (its number alone is a bulletin's, which it never replaces). */
const replaces = computed(() => (!grouped.value || groupOk(draft.group)) && props.ownBulletins.has(slotOf(draft)));

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
  if (offline.value !== undefined) return;
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
    :left-max="LIMITS.message.textMax"
    :left-title="leftTitle(left, 'characters', LIMITS.message.textMax)"
    @submit="submit"
  >
    <div class="field">
      <label for="post-kind">{{ t("bulletins.kind") }}</label>
      <div class="field-control">
        <select id="post-kind" v-model="draft.kind" class="input">
          <option v-for="k in POST_KINDS" :key="k.kind" :value="k.kind">{{ kindTitle(k.kind) }}</option>
        </select>
      </div>
    </div>
    <div class="field">
      <label for="post-id">{{ t(draft.kind === "announcement" ? "bulletins.letter" : "bulletins.number") }}</label>
      <div class="field-control">
        <select id="post-id" v-model="draft.id" class="input mono">
          <option v-for="c in idsOf(draft.kind)" :key="c" :value="c">{{ c }}</option>
        </select>
      </div>
    </div>
    <div class="field" :class="{ invalid: badGroup, disabled: !grouped }">
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
          :disabled="!grouped"
          autocomplete="off"
          spellcheck="false"
        />
      </div>
    </div>
    <div class="field">
      <label for="post-text">{{ t("bulletins.text") }}</label>
      <div class="field-control">
        <input
          id="post-text"
          :value="draft.text"
          class="input"
          type="text"
          autocomplete="off"
          @input="draft.text = typedInto($event, draft.text, limit)"
          @compositionend="draft.text = typedInto($event, draft.text, limit)"
        />
      </div>
    </div>
    <template #buttons>
      <button type="submit" class="btn primary" :disabled="!ready || rxOnly || offline !== undefined" :title="rxOnly ? rxOnlyReason() : offline">
        <TwoWords :second="replaces">
          <template #first>{{ t("bulletins.post") }}</template>
          <template #second>{{ t("bulletins.replace") }}</template>
        </TwoWords>
      </button>
    </template>
  </ComposeBar>
</template>
