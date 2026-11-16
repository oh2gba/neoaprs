<script setup lang="ts">
// The Bulletins tab: the message board filling the tab, newest first in four sections (announcements, bulletins, group messages, weather service), each row with
// who sent it, what it is addressed to (the group of a group bulletin, else the slot: BLN1, BLNA, QST), the text, how often it was heard and how long ago it was last heard. None of these is a conversation and none is answered;
// nothing ages out: a row stays until the delete button at its corner is pressed twice ("sure?"), which deletes it on the daemon. A right-click on a row (a long press on a touch screen) offers to copy its text and its sender's call (CopyMenu). A bulletin of ours is on the board too, marked "ours" (the call is ours), with how often it was sent
// and when it goes out next, and while several radios that can send are on the radios it goes out on as tags beside the mark, as Stations' "Heard on" names a station's radios (the first two by their names, then "+n"
// whose hover names the rest; with one radio on no row has one); its delete stops it and takes it off the board. An (i) at the top (TabHelp) says what a bulletin is. The box to post to the board is fixed at the bottom of the tab (components/BulletinCompose.vue), as the box of every tab. The board stays newest first
// in each section, as a board is read from the top: the sections and their headings keep their places (a stream oldest first, scrolled to the end, would open on the weather service).
import TagMark from "@/components/TagMark.vue";
import CopyMenu from "@/components/CopyMenu.vue";
import { computed } from "vue";
import BulletinCompose from "@/components/BulletinCompose.vue";
import IconButton from "@/components/IconButton.vue";
import TabHelp from "@/components/TabHelp.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useCopyMenu } from "@/composables/useCopyMenu";
import { useRadios } from "@/composables/useRadios";
import { useSure } from "@/composables/useSure";
import { t } from "@/i18n";
import { HEARD_ON_RADIOS, radioTone, titled } from "@/lib/channels";
import { dateTimeText } from "@/lib/format";
import type { PageRadio } from "@/lib/radios";
import { inForce } from "@/lib/sendon";
import { heardText, ownEntries, ownMeta, sections, targetOf, type BoardEntry } from "@/lib/bulletins";
import type { BulletinRow, OwnBulletinRow } from "@/protocol/protocol";

const props = defineProps<{ bulletins: ReadonlyMap<string, BulletinRow>; ownBulletins: ReadonlyMap<string, OwnBulletinRow> }>();
const { call, now, send } = useDaemonContext();
const { severalSenders: several, senders, byId } = useRadios();
/** The tags of a bulletin of ours: the radios it goes out on now, the first two by name, then "+n" whose hover names the rest; none with one radio on. */
const NONE = { shown: [], rest: [] } as const;
function tagsOf(own: OwnBulletinRow | undefined): { readonly shown: readonly PageRadio[]; readonly rest: readonly PageRadio[] } {
  if (own === undefined || !several.value) return NONE;
  const radios = inForce(
    own.radios,
    senders.value.map((radio) => radio.id),
  ).flatMap((id) => byId(id) ?? []);
  return { shown: radios.slice(0, HEARD_ON_RADIOS), rest: radios.slice(HEARD_ON_RADIOS) };
}
/** The hover words of a radio's tag: "Sent on radio 20 m". */
const sentOn = (radio: PageRadio): string => t("objects.sent_on", { name: radio.name });
const sure = useSure<string>(); // (the key of a row)
const keyOf = (b: BoardEntry) => (b.own ? `own/${b.slot}` : `${b.sender}/${b.slot}`);
const shown = computed(() => sections<BoardEntry>([...props.bulletins.values(), ...ownEntries(props.ownBulletins.values(), call.value ?? t("chain.you"))]));
/** The copy menu of a bulletin: its text, and its sender's call. */
const copy = useCopyMenu((item) => {
  const b = shown.value.flatMap((section) => section.rows).find((row) => keyOf(row) === item.dataset["key"]);
  return b === undefined
    ? []
    : [
        { kind: "message", text: b.text },
        { kind: "call", text: b.sender },
      ];
});
const remove = (b: BoardEntry): void =>
  void (b.own ? send({ cmd: "bulletin_unpost", slot: b.slot }) : send({ cmd: "bulletin_delete", sender: b.sender, slot: b.slot }));
</script>

<template>
  <div class="boardwrap">
    <TabHelp :label="t('bulletins.about_label')" picture="bulletin">
      <span class="info-line">{{ t("bulletins.about1") }}</span>
      <span class="info-line">{{ t("bulletins.about2") }}</span>
    </TabHelp>
    <div class="boardpane">
      <p v-if="shown.length === 0" class="empty">{{ t("bulletins.empty") }}</p>
      <fieldset v-for="section in shown" :key="section.kind" class="board-section" :aria-label="section.title">
        <legend class="board-title">
          {{ section.title }} <span class="muted">{{ section.rows.length }}</span>
        </legend>
        <ul class="board">
          <li
            v-for="b in section.rows"
            :key="keyOf(b)"
            class="bulletin copysource"
            tabindex="0"
            :class="{ mine: b.own !== undefined }"
            :data-key="keyOf(b)"
            v-on="copy.on.value"
          >
            <div class="bulletin-actions">
              <IconButton
                kind="delete"
                class="bulletin-delete"
                :title="b.own ? t('bulletins.delete_title') : undefined"
                :armed="sure.armed.value === keyOf(b)"
                :label="b.own ? t('bulletins.delete_own', { slot: b.slot }) : t('bulletins.delete', { slot: b.slot, sender: b.sender })"
                @click="sure.press(keyOf(b), () => remove(b))"
              />
            </div>
            <p class="bulletin-head">
              <strong class="mono">{{ b.sender }}</strong>
              <span class="muted">{{ ` ${t("bulletins.to")} ` }}</span>
              <span class="mono bulletin-target" :title="b.slot">{{ targetOf(b) }}</span>
              <TagMark v-if="b.own" tone="outline" class="own-mark">{{ t("bulletins.ours") }}</TagMark>
              <TagMark v-for="radio in tagsOf(b.own).shown" :key="radio.id" :tone="radioTone(radio)" class="own-radio" :title="sentOn(radio)">{{
                radio.name
              }}</TagMark>
              <TagMark v-if="tagsOf(b.own).rest.length > 0" tone="neutral" class="own-radio" :title="titled(tagsOf(b.own).rest.map(sentOn))"
                >{{ t("radio.more", { n: tagsOf(b.own).rest.length }) }}<span class="sr-only"> {{ titled(tagsOf(b.own).rest.map(sentOn)) }}</span></TagMark
              >
            </p>
            <p class="bulletin-text">{{ b.text }}</p>
            <p v-if="b.own" class="bulletin-meta muted" :title="t('bulletins.posted', { time: dateTimeText(b.first_heard) })">{{ ownMeta(b.own, now) }}</p>
            <p v-else class="bulletin-meta muted" :title="t('bulletins.heard_title', { first: dateTimeText(b.first_heard), last: dateTimeText(b.last_heard) })">
              {{ heardText(b.times_heard, b.last_heard, now) }}
            </p>
          </li>
        </ul>
      </fieldset>
    </div>
    <BulletinCompose
      :own-bulletins="ownBulletins"
      @post="(slot, text, radios) => send(radios === undefined ? { cmd: 'bulletin_post', slot, text } : { cmd: 'bulletin_post', slot, text, radios })"
    />
    <CopyMenu v-if="copy.menu.value" :key="copy.key.value" v-bind="copy.menu.value" @close="copy.close()" />
  </div>
</template>
