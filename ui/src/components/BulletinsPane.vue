<script setup lang="ts">
// The Bulletins tab: a box to post to the board on top (components/BulletinCompose.vue), and under it the message board, newest first in four sections (announcements, bulletins, group messages, weather service), each row with
// who sent it, what it is addressed to (the group of a group bulletin, else the slot: BLN1, BLNA, QST), the text, how often it was heard and how long ago it was last heard. None of these is a conversation and none is answered;
// nothing ages out: a row stays until the x at its corner is pressed twice ("sure?"), which deletes it on the daemon. A bulletin of ours is on the board too, marked "ours" (the call is ours), with how often it was sent
// and when it goes out next; its x stops it and takes it off the board.
import { computed } from "vue";
import BulletinCompose from "@/components/BulletinCompose.vue";
import { useSure } from "@/composables/useSure";
import { ageText, dateTimeText } from "@/lib/format";
import { ownEntries, ownMeta, sections, targetOf, timesText, type BoardEntry } from "@/lib/bulletins";
import type { BulletinRow, OwnBulletinRow } from "@/protocol/protocol";

const props = defineProps<{
  bulletins: ReadonlyMap<string, BulletinRow>;
  ownBulletins: ReadonlyMap<string, OwnBulletinRow>;
  call: string | null;
  now: number;
}>();
const emit = defineEmits<{ delete: [sender: string, slot: string]; post: [slot: string, text: string]; unpost: [slot: string] }>();
const sure = useSure<string>(); // (the key of a row)
const keyOf = (b: BoardEntry) => (b.own ? `own/${b.slot}` : `${b.sender}/${b.slot}`);
const shown = computed(() => sections<BoardEntry>([...props.bulletins.values(), ...ownEntries(props.ownBulletins.values(), props.call ?? "us")]));
const remove = (b: BoardEntry): void => (b.own ? emit("unpost", b.slot) : emit("delete", b.sender, b.slot));
</script>

<template>
  <div class="boardwrap">
    <BulletinCompose @post="(slot, text) => emit('post', slot, text)" />
    <div class="boardpane">
      <p v-if="shown.length === 0" class="empty">Nothing on the board.</p>
      <section v-for="section in shown" :key="section.kind" class="board-section" :aria-label="section.title">
        <h3 class="board-title">
          {{ section.title }} <span class="muted">{{ section.rows.length }}</span>
        </h3>
        <ul class="board">
          <li v-for="b in section.rows" :key="keyOf(b)" class="bulletin" :class="{ mine: b.own !== undefined }">
            <button
              type="button"
              class="conv-delete bulletin-delete"
              :class="{ danger: sure.armed.value === keyOf(b) }"
              :aria-label="b.own ? `Delete our bulletin ${b.slot}` : `Delete the bulletin ${b.slot} from ${b.sender}`"
              @click="sure.press(keyOf(b), () => remove(b))"
            >
              {{ sure.armed.value === keyOf(b) ? "sure?" : "x" }}
            </button>
            <p class="bulletin-head">
              <strong class="mono">{{ b.sender }}</strong>
              <span class="muted"> to </span>
              <span class="mono bulletin-target" :title="b.slot">{{ targetOf(b) }}</span>
              <span v-if="b.own" class="own-mark">ours</span>
            </p>
            <p class="bulletin-text">{{ b.text }}</p>
            <p v-if="b.own" class="bulletin-meta muted" :title="`posted ${dateTimeText(b.first_heard)}`">{{ ownMeta(b.own, now) }}</p>
            <p v-else class="bulletin-meta muted" :title="`first heard ${dateTimeText(b.first_heard)}, last heard ${dateTimeText(b.last_heard)}`">
              {{ timesText(b.times_heard) }}, {{ ageText(b.last_heard, now) }} ago
            </p>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
