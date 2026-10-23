<script setup lang="ts">
// Step 2 of the first-run guide: where the station is, in the look of the Location of the Beacon tab (components/SettingsLocation.vue). The big **Pick on the map** button comes first (it folds the guide to its head so that the whole map is free; the map shows a
// crosshair while it waits for the click, and a pin that can be dragged shows the place), with the place as one readable line ("60.42945 N, 24.14524 E · KP20le", "Not set"); latitude, longitude and the Maidenhead locator (6 characters: the centre
// of the square) are behind a closed "Enter coordinates or locator", which opens by itself only when a field is wrong. Next waits for a place.
import { computed } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import SettingsField from "@/components/SettingsField.vue";
import type { SetupGuide } from "@/composables/useSetupGuide";
import { positionToLocator } from "@/lib/locator";

const props = defineProps<{ guide: SetupGuide }>();
const degrees = { lat: { label: "Latitude", unit: "°", empty: "60.17" }, lon: { label: "Longitude", unit: "°", empty: "24.94" } };
const locator = { label: "Locator", empty: "KP20le" };

/** The place as the fields have it, in words: degrees with N or S, E or W, and the locator; "Not set" while there is none. */
const line = computed(() => {
  const at = props.guide.pin;
  if (at === null) return "Not set";
  const shown = (value: number) => String(Math.round(Math.abs(value) * 1e5) / 1e5);
  return `${shown(at.lat)} ${at.lat < 0 ? "S" : "N"}, ${shown(at.lon)} ${at.lon < 0 ? "W" : "E"} · ${positionToLocator(at.lat, at.lon)}`;
});
const wrong = computed(() => !!(props.guide.problems.lat || props.guide.problems.lon || props.guide.problems.locator));
</script>

<template>
  <div class="location">
    <button type="button" class="btn primary location-pick setup-onmap" @click="props.guide.peek(true)">Pick on the map</button>
    <span class="location-line" :class="{ muted: line === 'Not set' }">{{ line }}</span>
  </div>
  <DisclosureBox title="Enter coordinates or locator" :open="wrong">
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
  </DisclosureBox>
</template>
