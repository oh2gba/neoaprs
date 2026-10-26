<script setup lang="ts">
// One attempt's chips in a row, with an arrow between them (lib/chain.ts makes them).
import TagMark from "@/components/TagMark.vue";
import type { Chip } from "@/lib/chain";

defineProps<{ chips: readonly Chip[] }>();
</script>

<template>
  <ol class="chips">
    <li v-for="(chip, i) in chips" :key="i" class="chip-hop" :class="`hop-${chip.kind}`" :data-kind="chip.kind" :title="chip.title">
      <span v-if="i > 0" class="hop-arrow" aria-hidden="true">→</span><TagMark tone="outline" class="hop-call">{{ chip.text }}</TagMark
      ><span v-if="chip.mark !== ''" class="hop-mark">{{ chip.mark }}</span>
    </li>
  </ol>
</template>
