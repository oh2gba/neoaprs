<script setup lang="ts">
// The credits of the map: a small (i) in the corner, closed until it is clicked. OpenStreetMap's ODbL asks for its credit on every map made from its data, and the author of the symbol set
// asks for a pointer to the source. The credit of the map data is the licence's own wording and the same in every language; the other is a message of the catalogue.
import { ref } from "vue";
import { t } from "@/i18n";
import { ATTRIBUTION } from "@/lib/basemapstyle";

const open = ref(false);
</script>

<template>
  <div class="attrib">
    <div v-if="open" class="attrib-text">
      <p>{{ ATTRIBUTION }}</p>
      <p>{{ t("map.credits.symbols") }}</p>
    </div>
    <button
      class="attrib-toggle"
      type="button"
      :aria-expanded="open"
      :title="open ? t('map.credits.hide') : t('map.credits.show')"
      :aria-label="t('map.credits.show')"
      @click="open = !open"
    >
      i
    </button>
  </div>
</template>
