<script setup lang="ts">
// A small check mark for a station heard direct, with no repeater between: beside its call in
// the Stations table and on its card. It has the title "Heard direct", which a screen reader
// also gets.
import { t } from "@/i18n";
</script>

<template>
  <span class="direct-mark" role="img" :aria-label="t('station.direct.title')" :title="t('station.direct.title')">&#10003;</span>
</template>
