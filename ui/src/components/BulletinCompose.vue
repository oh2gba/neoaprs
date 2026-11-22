<script setup lang="ts">
// The box to post to the message board, at the bottom of the Bulletins tab (ComposeBar): kind,
// number, group (always present, greyed for other kinds so that nothing moves) and text with its
// counter. Post reads Replace when the slot holds a post of ours. The text clears when the
// daemon has the bulletin (topic `own_bulletins`); a refused one stays. While several sending
// radios are on, Send on ticks (SendOn.vue) choose the radios, applied by Post, which is off
// while none ticked is connected.
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
/** How long a bulletin and an announcement are sent, in the page's words. */
const hours = computed(() => t("bulletins.tip.hours", { n: LIMITS.bulletin.repeatHours }));
const days = computed(() => t("bulletins.tip.days", { n: LIMITS.bulletin.announcementRepeatDays }));
const draft = reactive<PostDraft>({ kind: "bulletin", id: "1", group: "", text: "" });

/** The message length limit (lib/textlimit.ts). */
const limit: TextLimit = { max: LIMITS.message.textMax, measure: trimmedCharacters, kind: "characters" };
const left = computed(() => leftOf(draft.text, limit));
const rxOnly = useReceiveOnly();
const page = inject(DAEMON_KEY, null);
const radios = useRadios();
const { told, named, severalSenders: several, all } = radios;
/** The draft's ticked radios; null until a tick is pressed, so a new draft follows the last
 * post. */
const chosen = ref<RadioId[] | null>(null);
const own = (): readonly RadioId[] =>
  chosen.value ?? (page?.status.value?.new_bulletin_radios ?? []).filter((id) => all.value.some((radio) => radio.id === id && !radio.removed));
/** Send on, bound to the draft. */
const { ticks, radios: on, tick } = useDraftSendOn(own, (ids) => (chosen.value = ids), "post", radios);
/** No ticked radio is on: Post is off until one is. */
const unticked = computed(() => several.value && on.value.length === 0);
/** Why no ticked radio can send (none connected, or none exist); undefined until radios are
 * known. */
const offline = computed(() => (unticked.value ? undefined : radiosBlockedReason(on.value, named, told.value)));
const ready = computed(() => canPost(draft));
const grouped = computed(() => draft.kind === "group");
const badGroup = computed(() => grouped.value && draft.group.trim() !== "" && !groupOk(draft.group));
/** Whether the chosen slot holds a post of ours, which the new text replaces. A group bulletin
 * without a group has no slot yet. */
const replaces = computed(() => (!grouped.value || groupOk(draft.group)) && props.ownBulletins.has(slotOf(draft)));

watch(
  () => draft.kind,
  (kind) => {
    if (!idsOf(kind).includes(draft.id)) draft.id = idsOf(kind).slice(0, 1);
  },
);

const socketOpen = useSocketOpen();
/** A post in flight until the daemon has it or refuses it. */
const posting = useCommandInFlight("bulletin_post", null);

const asked = ref<{ slot: string; text: string; before: OwnBulletinRow | undefined } | null>(null);

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
