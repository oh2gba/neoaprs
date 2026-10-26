<script setup lang="ts">
// The frame of every picture of an (i) note: a flat drawing 280 by 150 that scales down on a phone, drawn with the page's colours (styles/helppictures.css), described for a screen reader by the catalogue (`help.picture.<name>`). There is
// no text in the drawing but calls, frequencies and other words that are the same in every language, so that nothing in it needs translating.
import type { PictureName } from "@/help/names";
import { t } from "@/i18n";

defineProps<{ name: PictureName }>();
</script>

<template>
  <svg class="hp" viewBox="0 0 280 150" role="img" :aria-label="t(`help.picture.${name}`)" :data-picture="name">
    <slot></slot>
  </svg>
</template>
