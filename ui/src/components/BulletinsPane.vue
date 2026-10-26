<script setup lang="ts">
// The Bulletins tab: the message board filling the tab, newest first in four sections (announcements, bulletins, group messages, weather service), each row with
// who sent it, what it is addressed to (the group of a group bulletin, else the slot: BLN1, BLNA, QST), the text, how often it was heard and how long ago it was last heard. None of these is a conversation and none is answered;
// nothing ages out: a row stays until the delete button at its corner is pressed twice ("sure?"), which deletes it on the daemon. A bulletin of ours is on the board too, marked "ours" (the call is ours), with how often it was sent
// and when it goes out next; its delete stops it and takes it off the board. An (i) at the top (TabHelp) says what a bulletin is. The box to post to the board is fixed at the bottom of the tab (components/BulletinCompose.vue), as the box of every tab. The board stays newest first
// in each section, as a board is read from the top: the sections and their headings keep their places (a stream oldest first, scrolled to the end, would open on the weather service).
import TagMark from "@/components/TagMark.vue";
import { computed } from "vue";
import BulletinCompose from "@/components/BulletinCompose.vue";
import IconButton from "@/components/IconButton.vue";
import TabHelp from "@/components/TabHelp.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useSure } from "@/composables/useSure";
import { t } from "@/i18n";
import { dateTimeText } from "@/lib/format";
import { heardText, ownEntries, ownMeta, sections, targetOf, type BoardEntry } from "@/lib/bulletins";
import type { BulletinRow, OwnBulletinRow } from "@/protocol/protocol";

const props = defineProps<{ bulletins: ReadonlyMap<string, BulletinRow>; ownBulletins: ReadonlyMap<string, OwnBulletinRow> }>();
const { call, now, send } = useDaemonContext();
const sure = useSure<string>(); // (the key of a row)
const keyOf = (b: BoardEntry) => (b.own ? `own/${b.slot}` : `${b.sender}/${b.slot}`);
const shown = computed(() => sections<BoardEntry>([...props.bulletins.values(), ...ownEntries(props.ownBulletins.values(), call.value ?? "us")]));
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
          <li v-for="b in section.rows" :key="keyOf(b)" class="bulletin" :class="{ mine: b.own !== undefined }">
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
    <BulletinCompose :own-bulletins="ownBulletins" @post="(slot, text) => send({ cmd: 'bulletin_post', slot, text })" />
  </div>
</template>
