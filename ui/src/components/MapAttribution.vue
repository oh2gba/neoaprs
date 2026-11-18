<script setup lang="ts">
// The credits of the map: a small (i) in the corner, closed until it is clicked. OpenStreetMap's ODbL asks for its credit on every map made from its data, and the author of the symbol set
// asks for a pointer to the source, and so does the author of the list of device names (CC BY-SA 2.0). The credit of the map data is the licence's own wording and the same in every language; the other is a message of the catalogue.
// While the aircraft or the ships of a service are on the map (`credits`, composables/useMapTraffic.ts) its credit is there too, in the service's own words with its links (lib/layers/sources.ts), which open in a new tab;
// while aircraft are drawn (`aircraft`), the credit of their shapes (lib/layers/aircraftshapes.ts).
import { ref } from "vue";
import { t } from "@/i18n";
import { ATTRIBUTION } from "@/lib/basemapstyle";
import { CREDITS, type ServiceName } from "@/lib/layers/sources";

withDefaults(defineProps<{ credits?: readonly ServiceName[]; aircraft?: boolean }>(), { credits: () => [], aircraft: false });

const open = ref(false);
</script>

<template>
  <div class="attrib">
    <div v-if="open" class="attrib-text">
      <p>{{ ATTRIBUTION }}</p>
      <p>{{ t("map.credits.symbols") }}</p>
      <p>{{ t("map.credits.devices") }}</p>
      <p v-if="aircraft" class="attrib-shapes">{{ t("map.credits.aircraft") }}</p>
      <p v-for="source in credits" :key="source" class="attrib-layer" :data-source="source">
        <template v-for="(part, i) in CREDITS[source]" :key="i">
          <a v-if="part.href" :href="part.href" target="_blank" rel="noopener noreferrer">{{ part.text }}</a>
          <template v-else>{{ part.text }}</template>
        </template>
      </p>
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
