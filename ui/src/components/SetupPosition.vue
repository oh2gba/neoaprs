<script setup lang="ts">
// Step 2 of the first-run guide: the station's place, with the Location control (LocationField):
// Choose on map (folds the guide, shows a crosshair and a draggable pin), the place as text, and
// the latitude, longitude and Maidenhead locator fields. Next waits for a place.
import LocationField from "@/components/LocationField.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { placeOfText } from "@/lib/locator";

const { guide } = useDaemonContext();
</script>

<template>
  <LocationField
    id="setup"
    :place="placeOfText(guide.fields.lat, guide.fields.lon)"
    :picking="false"
    always-open
    :lat="guide.fields.lat"
    :lon="guide.fields.lon"
    :errors="{ lat: guide.problems.lat, lon: guide.problems.lon }"
    @pick="guide.peek(true)"
    @update:lat="guide.edit('lat', $event)"
    @update:lon="guide.edit('lon', $event)"
  />
</template>
