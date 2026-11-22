<script setup lang="ts">
// The map credits: a small (i) in the corner, closed until clicked. OpenStreetMap's ODbL, the
// symbol set and the device-name list (CC BY-SA 2.0) ask for credit; the map data credit is the
// licence's wording in every language. While aircraft or ships of a service are on the map
// (`credits`) its credit appears with its links, and the credit for the aircraft shapes while
// they are drawn (`aircraft`).
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
    <button class="attrib-toggle" type="button" :aria-expanded="open" :aria-label="open ? t('map.credits.hide') : t('map.credits.show')" @click="open = !open">
      i
    </button>
  </div>
</template>
