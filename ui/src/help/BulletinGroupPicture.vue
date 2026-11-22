<script setup lang="ts">
// How a group bulletin works: one station sends BLN3HAMS and all three stations hear it; the
// two following the group HAMS show it on their board, the third shows nothing.
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpLabel from "@/help/HelpLabel.vue";
import HelpStation from "@/help/HelpStation.vue";
import { arrow, waves } from "@/help/draw";

/** The three stations that hear it; those following the group show it and carry its name. */
const boards = [
  { y: 8, shown: true, group: "HAMS", code: ">" },
  { y: 56, shown: false, group: "", code: "-" },
  { y: 104, shown: true, group: "HAMS", code: ">" },
];
</script>

<template>
  <HelpFrame name="bulletingroup">
    <HelpStation table="/" code="-" :x="44" :y="56" :size="30" :label="t('help.me')" />
    <path class="hp-flow" :d="waves(62, 56, 0, 2, 8, 5)" />
    <rect class="hp-card hp-lit" x="9" y="92" width="54" height="40" rx="5" />
    <HelpLabel :x="36" :y="105" text="BLN3HAMS" />
    <path class="hp-dim" d="M16 114h40M16 124h28" />
    <template v-for="board in boards" :key="board.y">
      <path class="hp-flow" :d="arrow(80, 56, 112, board.y + 18)" />
      <HelpStation table="/" :code="board.code" :x="126" :y="board.y + 18" :size="24" :label="board.group" />
      <rect v-if="board.shown" class="hp-card hp-lit" :x="148" :y="board.y" width="128" height="36" rx="5" />
      <rect v-else class="hp-card hp-dim hp-dash" :x="148" :y="board.y" width="128" height="36" rx="5" />
      <template v-if="board.shown">
        <HelpLabel :x="156" :y="board.y + 14" text="BLN3HAMS" start />
        <path class="hp-dim" :d="`M156 ${board.y + 22}h104M156 ${board.y + 29}h64`" />
      </template>
    </template>
  </HelpFrame>
</template>
