<script setup lang="ts">
// The frame of every (i) note picture: a flat 280 by 150 drawing that scales down on a phone,
// in the page's colours (styles/helppictures.css), described for screen readers by the
// catalogue (`help.picture.<name>`). It holds no text except calls and frequencies, which are
// the same in every language.
import type { PictureName } from "@/help/names";
import { t } from "@/i18n";

defineProps<{ name: PictureName }>();
</script>

<template>
  <svg class="hp" viewBox="0 0 280 150" role="img" :aria-label="t(`help.picture.${name}`)" :data-picture="name">
    <slot></slot>
  </svg>
</template>
