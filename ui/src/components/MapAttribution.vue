<script setup lang="ts">
// The credits of the map: a small (i) in the corner, closed until it is clicked. OpenStreetMap's ODbL asks for its credit on every map made from its data, and the author of the symbol set
// asks for a pointer to the source, and so does the author of the list of device names (CC BY-SA 2.0). The credit of the map data is the licence's own wording and the same in every language; the other is a message of the catalogue.
import { computed, ref } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import { ATTRIBUTION } from "@/lib/basemapstyle";

const { config } = useDaemonContext();
/** The credits of the data drawn over the map besides the stations, while it is on: the ships of Digitraffic (CC BY 4.0) and the aircraft of adsb.fi. */
const more = computed(() =>
  (["ais", "adsb"] as const).filter((feed) => config.value?.values[`${feed}/enabled`] === "true").map((feed) => t(`settings.traffic.fold.licence.${feed}`)),
);
const open = ref(false);
</script>

<template>
  <div class="attrib">
    <div v-if="open" class="attrib-text">
      <p>{{ ATTRIBUTION }}</p>
      <p>{{ t("map.credits.symbols") }}</p>
      <p>{{ t("map.credits.devices") }}</p>
      <p v-for="line in more" :key="line">{{ line }}</p>
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
