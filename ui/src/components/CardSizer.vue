<script setup lang="ts">
// Drag handles for a sizable card: a strip along each edge and a square at each corner, over the
// card's own edge so that nothing moves while dragging. Pointer only: keyboard and screen reader
// users have the card's own keys (aria-keyshortcuts). Hidden where the card cannot be sized (a
// phone).
import type { CardSizing } from "@/composables/useCardSize";
import { EDGES, type Edge } from "@/lib/cardsize";

defineProps<{ sizing: CardSizing }>();

/** The class of each handle (styles/card.css), by edge or corner. */
const HANDLE: Readonly<Record<Edge, string>> = {
  n: "sizer-n",
  s: "sizer-s",
  e: "sizer-e",
  w: "sizer-w",
  ne: "sizer-ne",
  nw: "sizer-nw",
  se: "sizer-se",
  sw: "sizer-sw",
};
</script>

<template>
  <template v-if="sizing.enabled()">
    <span
      v-for="edge in EDGES"
      :key="edge"
      class="sizer"
      :class="HANDLE[edge]"
      aria-hidden="true"
      v-on="sizing.handle"
      @pointerdown="sizing.down($event, edge)"
    />
  </template>
</template>
