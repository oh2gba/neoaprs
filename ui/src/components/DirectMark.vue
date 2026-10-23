<script setup lang="ts">
// A small green check mark for a station heard direct, with no repeater between us: beside its call in the Stations table and on its card. The green is the page's "ok" colour (it has its own value in the dark scheme); it is not the only cue: the mark is a
// check mark, has the hover title "Heard direct" and is named so for a screen reader.
</script>

<template>
  <span class="direct-mark" role="img" aria-label="Heard direct" title="Heard direct">&#10003;</span>
</template>
