<script setup lang="ts">
// Step 2 of the first-run guide: where the station is. Latitude and longitude, or the Maidenhead locator (6 characters: the centre of the square), or this computer's place from the browser, or a click on the map (the guide's `place`, called
// from the page); the marker on the map shows what the fields say. A browser that refuses to say, or has no place to give, is passed over without a word.
import { ref } from "vue";
import SettingsField from "@/components/SettingsField.vue";
import type { SetupGuide } from "@/composables/useSetupGuide";

const props = defineProps<{ guide: SetupGuide }>();
const degrees = { lat: { label: "Latitude", unit: "°", empty: "60.17" }, lon: { label: "Longitude", unit: "°", empty: "24.94" } };
const locator = { label: "Locator", empty: "KP20le" };
const locating = ref(false);
const canLocate = typeof navigator !== "undefined" && "geolocation" in navigator;

function locate(): void {
  locating.value = true;
  navigator.geolocation.getCurrentPosition(
    (here) => {
      locating.value = false;
      props.guide.place(here.coords.latitude, here.coords.longitude);
    },
    () => {
      locating.value = false;
    },
    { timeout: 15000, maximumAge: 600000 },
  );
}
</script>

<template>
  <SettingsField
    id="setup-lat"
    :info="degrees.lat"
    :model-value="props.guide.fields.lat"
    fallback=""
    :error="props.guide.problems.lat ?? ''"
    :changed="false"
    @update:model-value="props.guide.edit('lat', $event)"
  />
  <SettingsField
    id="setup-lon"
    :info="degrees.lon"
    :model-value="props.guide.fields.lon"
    fallback=""
    :error="props.guide.problems.lon ?? ''"
    :changed="false"
    @update:model-value="props.guide.edit('lon', $event)"
  />
  <SettingsField
    id="setup-locator"
    :info="locator"
    :model-value="props.guide.fields.locator"
    fallback=""
    :error="props.guide.problems.locator ?? ''"
    :changed="false"
    @update:model-value="props.guide.edit('locator', $event)"
  />
  <div class="setup-actions">
    <button v-if="canLocate" type="button" class="btn" :disabled="locating" @click="locate">Use this computer's location</button>
    <button type="button" class="btn setup-onmap" @click="props.guide.peek(true)">On the map</button>
  </div>
</template>
