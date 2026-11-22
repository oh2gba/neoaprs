<script setup lang="ts">
// The group box to post to the message board, at the bottom of the Bulletins tab (ComposeBar, as everywhere; the fields are rows like those of the Objects form). Each row has its (i) after the control, as the object form's rows have (InfoTip): what the kind, the place, the group and the text are, the kind's and the group's with a small picture.
// The kind is a choice whose options say what each does (a bulletin and an announcement differ in how long they are repeated, a group bulletin in whom it is for: lib/bulletins.ts `kindTitle`, with the daemon's own
// numbers); under it the number the post has (a capital letter for an announcement, the same row), the group of a group bulletin (its row is always there, greyed for the other kinds, so that choosing a kind moves
// nothing) and the text, with the characters it has left. Post is on when the text can be sent (printable ASCII without | ~ {) and, for a group, the group is one to five letters and digits; it says Replace while the
// number, letter or group chosen holds a post of ours, which the new text replaces (both words are in the button, TwoWords: it is as wide as the longer). The text is
// cleared when the daemon has the bulletin (the topic `own_bulletins` tells it); one it refused stays for the user to correct. Under the text, while several radios that can send are on, Send on (SendOn.vue, the beacon's
// row, bound to the draft and applied by Post, as the object form's by Save): a tick for each radio, those the bulletin goes out on ticked, a new draft as the bulletin posted last (the daemon's
// `status.new_bulletin_radios`), the last tick greyed; Post sends the ticks with the text, so that a text for a slot that holds one of ours replaces its ticks too. The row comes and goes only with the radios (in
// Settings), and the counter and Post stay at the foot of the box. Post is off while none of the radios ticked is connected, with that as its reason (each named while several are on), as Send is.
import { DAEMON_KEY } from "@/composables/useDaemonContext";
import { useCommandInFlight, useSocketOpen } from "@/composables/useInFlight";
import { useRadios } from "@/composables/useRadios";
import { useReceiveOnly } from "@/composables/useReceiveOnly";
import { useDraftSendOn } from "@/composables/useSendOn";
import { rxOnlyReason } from "@/lib/compose";
import type { RadioId } from "@/lib/radios";
import { radiosBlockedReason } from "@/lib/sendon";
import { computed, inject, reactive, ref, watch } from "vue";
import ComposeBar from "@/components/ComposeBar.vue";
import InfoTip from "@/components/InfoTip.vue";
import SendOn from "@/components/SendOn.vue";
import TwoWords from "@/components/TwoWords.vue";
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { leftTitle } from "@/lib/compose";
import { LIMITS } from "@/protocol/lists";
import type { OwnBulletinRow } from "@/protocol/protocol";
import { leftOf, type TextLimit, trimmedCharacters, typedInto } from "@/lib/textlimit";
import { GROUP_MAX, POST_KINDS, canPost, groupOf, groupOk, idsOf, kindTitle, postCommand, slotOf, type PostDraft } from "@/lib/bulletins";

const props = defineProps<{ ownBulletins: ReadonlyMap<string, OwnBulletinRow> }>();
const emit = defineEmits<{ post: [slot: string, text: string, radios?: RadioId[]] }>();
const about = (field: MessageId) => t("settings.about", { label: t(field) });
const forbidden = [...LIMITS.message.forbidden].join(" ");
/** How long a bulletin and an announcement are sent, in the words of the page (the daemon's own numbers). */
const hours = computed(() => t("bulletins.tip.hours", { n: LIMITS.bulletin.repeatHours }));
const days = computed(() => t("bulletins.tip.days", { n: LIMITS.bulletin.announcementRepeatDays }));
const draft = reactive<PostDraft>({ kind: "bulletin", id: "1", group: "", text: "" });

/** The characters of a message; the field takes no more (lib/textlimit.ts, as every field with a counter). */
const limit: TextLimit = { max: LIMITS.message.textMax, measure: trimmedCharacters, kind: "characters" };
const left = computed(() => leftOf(draft.text, limit));
const rxOnly = useReceiveOnly();
const page = inject(DAEMON_KEY, null);
const radios = useRadios();
const { told, named, severalSenders: several, all } = radios;
/** The radios ticked in the draft; null until a tick is pressed: a new draft starts as the bulletin posted last, as the daemon says it. */
const chosen = ref<RadioId[] | null>(null);
const own = (): readonly RadioId[] =>
  chosen.value ?? (page?.status.value?.new_bulletin_radios ?? []).filter((id) => all.value.some((radio) => radio.id === id && !radio.removed));
/** Send on, bound to the draft: the ticks, and the radios the bulletin goes out on as they stand. */
const { ticks, radios: on, tick } = useDraftSendOn(own, (ids) => (chosen.value = ids), "post", radios);
/** No tick is ticked (the radios ticked are off): Post is off until one is, with no title (the row of ticks shows it). */
const unticked = computed(() => several.value && on.value.length === 0);
/** Why nothing may go on the radios ticked: none of them is connected (each named where several are on), or there is none; undefined before the daemon has told its radios. */
const offline = computed(() => (unticked.value ? undefined : radiosBlockedReason(on.value, named, told.value)));
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

const socketOpen = useSocketOpen();
/** A post in flight until the daemon has it (its row is told) or refused it. */
const posting = useCommandInFlight("bulletin_post", null);

const asked = ref<{ slot: string; text: string; before: OwnBulletinRow | undefined } | null>(null); // what was posted, until the daemon has it

watch(
  () => (asked.value === null ? undefined : props.ownBulletins.get(asked.value.slot)),
  (row) => {
    const sent = asked.value;
    if (sent === null || row === undefined || row === sent.before || row.text !== sent.text) return;
    asked.value = null;
    posting.land();
    if (draft.text.trim() === sent.text) draft.text = "";
  },
);

function submit(): void {
  if (offline.value !== undefined || unticked.value || !socketOpen.value || posting.busy.value) return;
  const command = postCommand(draft);
  if (command === null) return;
  draft.group = groupOf(draft.group);
  asked.value = { slot: command.slot, text: command.text, before: props.ownBulletins.get(command.slot) };
  posting.run(() => {
    if (several.value)
      emit(
        "post",
        command.slot,
        command.text,
        on.value.map((radio) => radio.id),
      );
    else emit("post", command.slot, command.text);
    return true;
  });
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
        <InfoTip :label="about('bulletins.kind')" picture="bulletin">
          <span class="info-line">{{ t("bulletins.tip.kind1", { hours, days }) }}</span>
          <span class="info-line">{{ t("bulletins.tip.kind2", { hours }) }}</span>
        </InfoTip>
      </div>
    </div>
    <div class="field">
      <label for="post-id">{{ t(draft.kind === "announcement" ? "bulletins.letter" : "bulletins.number") }}</label>
      <div class="field-control">
        <select id="post-id" v-model="draft.id" class="input mono">
          <option v-for="c in idsOf(draft.kind)" :key="c" :value="c">{{ c }}</option>
        </select>
        <InfoTip :label="about(draft.kind === 'announcement' ? 'bulletins.letter' : 'bulletins.number')">
          <span class="info-line">{{ t("bulletins.tip.id1") }}</span>
          <span class="info-line">{{ t("bulletins.tip.id2") }}</span>
        </InfoTip>
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
        <InfoTip :label="about('bulletins.group')" picture="bulletingroup">
          <span class="info-line">{{ t("bulletins.tip.group1") }}</span>
          <span class="info-line">{{ t("bulletins.tip.group2") }}</span>
        </InfoTip>
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
        <InfoTip :label="about('bulletins.text')">
          <span class="info-line">{{ t("bulletins.tip.text1", { max: LIMITS.message.textMax, forbidden }) }}</span>
          <span class="info-line">{{ t("bulletins.tip.text2") }}</span>
        </InfoTip>
      </div>
    </div>
    <SendOn v-if="ticks.length > 0" id="post-send-on" class="send-on" :ticks="ticks" error="" @tick="tick" />
    <template #buttons>
      <button
        type="submit"
        class="btn primary"
        :disabled="!ready || rxOnly || unticked || offline !== undefined || !socketOpen || posting.busy.value"
        :title="rxOnly ? rxOnlyReason() : offline"
      >
        <TwoWords :second="replaces">
          <template #first>{{ t("bulletins.post") }}</template>
          <template #second>{{ t("bulletins.replace") }}</template>
        </TwoWords>
      </button>
    </template>
  </ComposeBar>
</template>
