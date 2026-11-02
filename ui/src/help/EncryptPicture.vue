<script setup lang="ts">
// Encrypted messages: on the upper line the two stations give each other their keys (a key goes each way). On the lower line our message goes out locked (the padlock on the bubble): the other station, which has the key, reads it,
// and a third station that hears it too sees only the lock (its bubble is dim and crossed out).
import { CALLS } from "@/help/calls";
import { arrow } from "@/help/draw";
import { t } from "@/i18n";
import HelpFrame from "@/help/HelpFrame.vue";
import HelpStation from "@/help/HelpStation.vue";

/** A key, drawn with its ring at (x, y) and its blade to the right. */
const key = (x: number, y: number): string => `M${x} ${y}m-3 0a3 3 0 1 0 6 0a3 3 0 1 0 -6 0M${x + 3} ${y}h11M${x + 10} ${y}v3M${x + 14} ${y}v2`;
/** A padlock with its body's top-left corner at (x, y), 9 wide. */
const lock = (x: number, y: number): string => `M${x} ${y}h9v7h-9zM${x + 2} ${y}v-2.2a2.5 2.5 0 0 1 5 0V${y}`;
</script>

<template>
  <HelpFrame name="encrypt">
    <HelpStation table="/" code="-" :x="40" :y="40" :size="28" :label="t('help.me')" />
    <HelpStation table="/" code=">" :x="240" :y="40" :label="CALLS.otherCar" />
    <path class="hp-flow" :d="arrow(66, 30, 212, 30)" />
    <path class="hp-solid" :d="key(104, 20)" />
    <path class="hp-flow" :d="arrow(214, 50, 68, 50)" />
    <path class="hp-solid" :d="key(160, 60)" />

    <HelpStation table="/" code="-" :x="40" :y="112" :size="28" :label="t('help.me')" />
    <path class="hp-card hp-lit" d="M80 112l-3 7 11-7" />
    <rect class="hp-card hp-lit" x="72" y="92" width="56" height="20" rx="7" />
    <path class="hp-on-accent" :d="lock(95, 100)" />
    <path class="hp-flow" :d="arrow(132, 104, 212, 104)" />
    <HelpStation table="/" code=">" :x="240" :y="112" :label="CALLS.otherCar" />
    <path class="hp-dim" :d="arrow(132, 112, 166, 136)" />
    <rect class="hp-card hp-faded" x="168" y="124" width="40" height="18" rx="9" />
    <path class="hp-dim" :d="lock(184, 128)" />
    <path class="hp-bad" d="M172 126l32 14m0-14l-32 14" />
  </HelpFrame>
</template>
