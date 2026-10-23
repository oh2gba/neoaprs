<script setup lang="ts">
// The credits of the map: a small (i) in the corner, closed until it is clicked. OpenStreetMap's ODbL asks for its credit on every map made from its data, and the author of the symbol set
// asks for a pointer to the source.
import { ref } from "vue";
import { ATTRIBUTION, SYMBOLS_ATTRIBUTION } from "@/lib/basemapstyle";

const open = ref(false);
</script>

<template>
  <div class="attrib">
    <div v-if="open" class="attrib-text">
      <p>{{ ATTRIBUTION }}</p>
      <p>{{ SYMBOLS_ATTRIBUTION }}</p>
    </div>
    <button
      class="attrib-toggle"
      type="button"
      :aria-expanded="open"
      :title="open ? 'Hide the credits' : 'Map and symbol credits'"
      aria-label="Map and symbol credits"
      @click="open = !open"
    >
      i
    </button>
  </div>
</template>
