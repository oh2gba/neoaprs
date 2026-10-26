<script setup lang="ts">
// THE small mark of the page, one component and one look (styles/tag.css): the count of the header and of a tab, the state of the radio, the iGate or the GPS, the channel a station was heard by, "Receive only", a hop of a message's chain, a call to take off a group.
// Shape, height, font and padding are the same everywhere; only the colour says what it is, and it is always a soft pair of the palette (styles/tokens.css): `accent` (something to look at: a count), `neutral` (a label), `ok`, `warn`, `bad`, `info` (the four meanings), `dummy` (made up: neutral with a dashed border),
// `outline` (the colour of the text, for a mark inside a text that is already coloured). A mark that is pressed is `as="button"`.
export type TagTone = "accent" | "neutral" | "ok" | "warn" | "bad" | "info" | "dummy" | "outline";

/** The class of each tone, written out so that the style sheet's rules are found by name. */
const TONE_CLASS: Record<TagTone, string> = {
  accent: "tag-accent",
  neutral: "tag-neutral",
  ok: "tag-ok",
  warn: "tag-warn",
  bad: "tag-bad",
  info: "tag-info",
  dummy: "tag-dummy",
  outline: "tag-outline",
};

withDefaults(defineProps<{ tone?: TagTone; as?: "span" | "button" }>(), { tone: "accent", as: "span" });
</script>

<template>
  <component :is="as" class="tag" :class="TONE_CLASS[tone]" :type="as === 'button' ? 'button' : undefined"><slot></slot></component>
</template>
