<script setup lang="ts">
// Step 2 of the first-run guide: where the station is. Latitude and longitude, or the Maidenhead locator (6 characters: the centre of the square), or a click on the map (the guide's `place`, called from the page), or the pin
// dragged; the pin on the map shows what the fields say. "Pick on the map" folds the guide to its head so that the whole map is free; the map shows a crosshair while it waits for the click.
import SettingsField from "@/components/SettingsField.vue";
import type { SetupGuide } from "@/composables/useSetupGuide";

const props = defineProps<{ guide: SetupGuide }>();
const degrees = { lat: { label: "Latitude", unit: "°", empty: "60.17" }, lon: { label: "Longitude", unit: "°", empty: "24.94" } };
const locator = { label: "Locator", empty: "KP20le" };
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
    <button type="button" class="btn setup-onmap" @click="props.guide.peek(true)">Pick on the map</button>
  </div>
</template>
