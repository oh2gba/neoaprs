<script setup lang="ts">
// The small mark of the page, one component and one look (styles/tag.css): the count of the
// header and tabs, the state of a radio, iGate or GPS, the channel a station was heard by,
// "Receive only", a hop of a message chain, a call to remove from a group. Shape, height, font
// and padding are the same everywhere; only the colour differs, always a soft pair of the
// palette (styles/tokens.css): `accent` (a count), `neutral` (a label), `ok`, `warn`, `bad`,
// `info` (the four meanings), `hf` (the HF radio's channel: inverse pill), `lora` (a LoRa
// radio's: sage), `dummy` (made up: neutral, dashed border), `removed` (a removed radio: quiet
// words, no plate, thin edge), `outline` (text colour, for a mark inside coloured text).
// A pressed mark is `as="button"`.
export type TagTone =
  "accent" | "neutral" | "ok" | "warn" | "bad" | "info" | "hf" | "lora" | "dummy" | "removed" | "outline";

/** The class of each tone, written out so that the style sheet's rules are found by name. */
const TONE_CLASS: Record<TagTone, string> = {
  accent: "tag-accent",
  neutral: "tag-neutral",
  ok: "tag-ok",
  warn: "tag-warn",
  bad: "tag-bad",
  info: "tag-info",
  hf: "tag-hf",
  lora: "tag-lora",
  dummy: "tag-dummy",
  removed: "tag-removed",
  outline: "tag-outline",
};

withDefaults(defineProps<{ tone?: TagTone; as?: "span" | "button" }>(), { tone: "accent", as: "span" });
</script>

<template>
  <component :is="as" class="tag" :class="TONE_CLASS[tone]" :type="as === 'button' ? 'button' : undefined"
    ><slot></slot
  ></component>
</template>
