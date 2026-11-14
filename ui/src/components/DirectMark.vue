<script setup lang="ts">
// A small check mark for a station heard direct, with no repeater between us: beside its call in the Stations table and on its card. It is in the page's "ok" colour, the plain text; it is not the only cue: the mark is a
// check mark, has the hover title "Heard direct" and is named so for a screen reader.
import { t } from "@/i18n";
</script>

<template>
  <span class="direct-mark" role="img" :aria-label="t('station.direct.title')" :title="t('station.direct.title')">&#10003;</span>
</template>
