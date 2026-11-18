<script setup lang="ts">
// The handles of a card that is sized (composables/useCardSize.ts): a strip along each edge and a square at each corner, over the card's own edge, so that nothing moves while one is dragged. A screen reader hears each as a handle
// for the pointer only: a screen reader and the keyboard have the card's own keys (aria-keyshortcuts on the card, said on its head by station.card.size_title). Not shown where the card cannot be sized (a phone).
import type { CardSizing } from "@/composables/useCardSize";
import { EDGES } from "@/lib/cardsize";

defineProps<{ sizing: CardSizing }>();
</script>

<template>
  <template v-if="sizing.enabled()">
    <span
      v-for="edge in EDGES"
      :key="edge"
      class="sizer"
      :class="`sizer-${edge}`"
      aria-hidden="true"
      v-on="sizing.handle"
      @pointerdown="sizing.down($event, edge)"
    />
  </template>
</template>
