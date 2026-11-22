<script setup lang="ts">
// The box to post to the message board, at the bottom of the Bulletins tab (ComposeBar): kind, how
// long it is sent (the station's choice for the kind until one is made), group (always present,
// greyed for other kinds so that nothing moves) and text with its counter. The daemon puts the post
// in the next free slot; Post is off while the kind has none. The text clears when the daemon has
// the post (topic `own_bulletins`); a refused one stays. While several sending radios are on, Send
// on ticks (SendOn.vue) choose the radios, applied by Post, which is off while none ticked is
// connected.
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
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { leftTitle } from "@/lib/compose";
import { LIMITS } from "@/protocol/lists";
import type { OwnBulletinRow } from "@/protocol/protocol";
import { leftOf, type TextLimit, trimmedCharacters, typedInto } from "@/lib/textlimit";
import {
  GROUP_MAX,
  POST_KINDS,
  canPost,
  groupOf,
  groupOk,
  kindTitle,
  postCommand,
  rememberedHours,
  sentForChoices,
  sentForText,
  type PostCommand,
  type PostDraft,
} from "@/lib/bulletins";

const props = defineProps<{ ownBulletins: ReadonlyMap<string, OwnBulletinRow> }>();
const emit = defineEmits<{ post: [command: PostCommand] }>();
const about = (field: MessageId) => t("settings.about", { label: t(field) });
const forbidden = [...LIMITS.message.forbidden].join(" ");
const draft = reactive<PostDraft>({ kind: "bulletin", hours: null, group: "", text: "" });

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
  chosen.value ??
  (page?.status.value?.new_bulletin_radios ?? []).filter((id) =>
    all.value.some((radio) => radio.id === id && !radio.removed),
  );
/** Send on, bound to the draft. */
const { ticks, radios: on, tick } = useDraftSendOn(own, (ids) => (chosen.value = ids), "post", radios);
/** No ticked radio is on: Post is off until one is. */
const unticked = computed(() => several.value && on.value.length === 0);
/** Why no ticked radio can send (none connected, or none exist); undefined until radios are
 * known. */
const offline = computed(() => (unticked.value ? undefined : radiosBlockedReason(on.value, named, told.value)));
const ready = computed(() => canPost(draft, props.ownBulletins));
const grouped = computed(() => draft.kind === "group");
const badGroup = computed(() => grouped.value && draft.group.trim() !== "" && !groupOk(draft.group));
/** Sent for as shown: the draft's choice, else the station's for the kind. */
const hours = computed({
  get: () => draft.hours ?? rememberedHours(draft.kind, page?.status.value?.new_bulletin_hours),
  set: (chosen: number) => (draft.hours = chosen),
});

watch(
  () => draft.kind,
  () => (draft.hours = null),
);

const socketOpen = useSocketOpen();
/** A post in flight until the daemon has it or refuses it. */
const posting = useCommandInFlight("bulletin_post", null);

/** The post in flight and the slots of ours when it was sent: it has landed when a new slot holds it. */
const asked = ref<{ command: PostCommand; before: ReadonlySet<string> } | null>(null);

watch(
  () => (asked.value === null ? undefined : landed(asked.value.command, asked.value.before)),
  (row) => {
    const sent = asked.value;
    if (sent === null || row === undefined) return;
    asked.value = null;
    posting.land();
    if (draft.text.trim() === sent.command.text) draft.text = "";
  },
);

function landed(command: PostCommand, before: ReadonlySet<string>): OwnBulletinRow | undefined {
  for (const [slot, row] of props.ownBulletins)
    if (
      !before.has(slot) &&
      row.kind === command.kind &&
      row.group === (command.group ?? "") &&
      row.text === command.text
    )
      return row;
  return undefined;
}

function submit(): void {
  if (offline.value !== undefined || unticked.value || !socketOpen.value || posting.busy.value) return;
  const command = postCommand(
    draft,
    hours.value,
    props.ownBulletins,
    several.value ? on.value.map((radio) => radio.id) : undefined,
  );
  if (command === null) return;
  draft.group = groupOf(draft.group);
  asked.value = { command, before: new Set(props.ownBulletins.keys()) };
  posting.run(() => {
    emit("post", command);
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
          <option v-for="kind in POST_KINDS" :key="kind" :value="kind">{{ kindTitle(kind) }}</option>
        </select>
        <InfoTip :label="about('bulletins.kind')" picture="bulletin">
          <span class="info-line">{{ t("bulletins.tip.kinds1") }}</span>
          <span class="info-line">{{ t("bulletins.tip.kinds2") }}</span>
        </InfoTip>
      </div>
    </div>
    <div class="field">
      <label for="post-sent-for">{{ t("bulletins.sent_for") }}</label>
      <div class="field-control">
        <select id="post-sent-for" v-model.number="hours" class="input">
          <option v-for="choice in sentForChoices(draft.kind)" :key="choice" :value="choice">
            {{ sentForText(draft.kind, choice) }}
          </option>
        </select>
        <InfoTip :label="about('bulletins.sent_for')">
          <span class="info-line">{{ t("bulletins.tip.sent_for") }}</span>
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
          <span class="info-line">{{ t("bulletins.tip.text_repeat") }}</span>
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
        {{ t("bulletins.post") }}
      </button>
    </template>
  </ComposeBar>
</template>
