<script setup lang="ts">
// The Bulletins tab: the message board, newest first in four sections (announcements, bulletins, group messages, weather service), each row with who sent it, what it is addressed to (the group of a group bulletin,
// else the slot: BLN1, BLNA, QST), the text, how often it was heard and how long ago it was last heard. None of these is a conversation and none is answered; nothing ages out: a row stays until the x at its
// corner is pressed twice ("sure?"), which deletes it on the daemon.
import { computed } from "vue";
import { useSure } from "@/composables/useSure";
import { ageText, dateTimeText } from "@/lib/format";
import { sections, targetOf, timesText } from "@/lib/bulletins";
import type { BulletinRow } from "@/protocol/protocol";

const props = defineProps<{ bulletins: ReadonlyMap<string, BulletinRow>; now: number }>();
const emit = defineEmits<{ delete: [sender: string, slot: string] }>();
const sure = useSure<string>(); // (sender/slot of a row)
const keyOf = (b: BulletinRow) => `${b.sender}/${b.slot}`;
const shown = computed(() => sections(props.bulletins.values()));
</script>

<template>
  <div class="boardpane">
    <p v-if="shown.length === 0" class="empty">Nothing on the board.</p>
    <section v-for="section in shown" :key="section.kind" class="board-section" :aria-label="section.title">
      <h3 class="board-title">
        {{ section.title }} <span class="muted">{{ section.rows.length }}</span>
      </h3>
      <ul class="board">
        <li v-for="b in section.rows" :key="keyOf(b)" class="bulletin">
          <button
            type="button"
            class="conv-delete bulletin-delete"
            :class="{ danger: sure.armed.value === keyOf(b) }"
            :aria-label="`Delete the bulletin ${b.slot} from ${b.sender}`"
            @click="sure.press(keyOf(b), () => emit('delete', b.sender, b.slot))"
          >
            {{ sure.armed.value === keyOf(b) ? "sure?" : "x" }}
          </button>
          <p class="bulletin-head">
            <strong class="mono">{{ b.sender }}</strong>
            <span class="muted"> to </span>
            <span class="mono bulletin-target" :title="b.slot">{{ targetOf(b) }}</span>
          </p>
          <p class="bulletin-text">{{ b.text }}</p>
          <p class="bulletin-meta muted" :title="`first heard ${dateTimeText(b.first_heard)}, last heard ${dateTimeText(b.last_heard)}`">
            {{ timesText(b.times_heard) }}, {{ ageText(b.last_heard, now) }} ago
          </p>
        </li>
      </ul>
    </section>
  </div>
</template>
