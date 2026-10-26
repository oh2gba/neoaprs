<script setup lang="ts">
// THE small mark of the page, one component and one look (styles/tag.css): the count of the header and of a tab, the state of the radio, the iGate or the GPS, the channel a station was heard by, "Receive only", a hop of a message's chain, a call to take off a group.
// Shape, height, font and padding are the same everywhere; only the colour says what it is: `count` (blue: something to look at), `quiet` (a label), `muted`, `ok` and `warn` (a state; a more exact class sets the colour of each state), `outline` (the colour of the text, for a mark inside a text that is already coloured),
// `warn-outline`. A mark that is pressed is `as="button"`.
export type TagTone = "count" | "quiet" | "muted" | "ok" | "warn" | "outline" | "warn-outline";

withDefaults(defineProps<{ tone?: TagTone; as?: "span" | "button" }>(), { tone: "count", as: "span" });
</script>

<template>
  <component :is="as" class="tag" :class="`tag-${tone}`" :type="as === 'button' ? 'button' : undefined"><slot></slot></component>
</template>
