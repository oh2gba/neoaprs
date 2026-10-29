<script setup lang="ts">
// Step 2 of the first-run guide: where the station is, with the Location control of the My station tab and of the Objects form (components/LocationField.vue): **Choose on map** (it folds the guide to its head so that the whole map is free; the map shows a crosshair while it waits for the click, and a pin that
// can be dragged shows the place), the place as text ("60.42945 N, 24.14524 E · KP20le", "Not set") and, open the whole time, the latitude, the longitude and the Maidenhead locator (6 characters: the centre of the square). Next waits for a place.
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
