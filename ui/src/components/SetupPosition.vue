<script setup lang="ts">
// Step 2 of the first-run guide: where the station is, in the look of the Location of the Beacon tab (components/SettingsLocation.vue). The big **Pick on the map** button comes first (it folds the guide to its head so that the whole map is free; the map shows a
// crosshair while it waits for the click, and a pin that can be dragged shows the place), with the place as one readable line ("60.42945 N, 24.14524 E · KP20le", "Not set"); latitude, longitude and the Maidenhead locator (6 characters: the centre
// of the square) are behind a closed "Enter coordinates or locator", which opens by itself only when a field is wrong. Next waits for a place.
import { computed } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import SettingsField from "@/components/SettingsField.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { positionToLocator } from "@/lib/locator";

const { guide } = useDaemonContext();
/** The fields' own words, made when the page is drawn so that they follow the language. */
const degrees = (key: "lat" | "lon") => ({
  label: t(key === "lat" ? "settings.lat.label" : "settings.lon.label"),
  unit: "°",
  empty: key === "lat" ? "60.17" : "24.94",
});
const locator = () => ({ label: t("setup.locator.label"), empty: "KP20le" });

/** The place as the fields have it, in words: degrees with N or S, E or W, and the locator; null while there is none. */
const place = computed(() => {
  const at = guide.pin;
  if (at === null) return null;
  const shown = (value: number) => String(Math.round(Math.abs(value) * 1e5) / 1e5);
  return `${shown(at.lat)} ${at.lat < 0 ? "S" : "N"}, ${shown(at.lon)} ${at.lon < 0 ? "W" : "E"} · ${positionToLocator(at.lat, at.lon)}`;
});
const wrong = computed(() => !!(guide.problems.lat || guide.problems.lon || guide.problems.locator));
</script>

<template>
  <div class="location">
    <button type="button" class="btn primary location-pick setup-onmap" @click="guide.peek(true)">{{ t("settings.location.pick") }}</button>
    <span class="location-line" :class="{ muted: place === null }">{{ place ?? t("settings.location.not_set") }}</span>
  </div>
  <DisclosureBox :title="t('setup.enter_coordinates')" :open="wrong">
    <SettingsField
      id="setup-lat"
      :info="degrees('lat')"
      :model-value="guide.fields.lat"
      fallback=""
      :error="guide.problems.lat ?? ''"
      :changed="false"
      @update:model-value="guide.edit('lat', $event)"
    />
    <SettingsField
      id="setup-lon"
      :info="degrees('lon')"
      :model-value="guide.fields.lon"
      fallback=""
      :error="guide.problems.lon ?? ''"
      :changed="false"
      @update:model-value="guide.edit('lon', $event)"
    />
    <SettingsField
      id="setup-locator"
      :info="locator()"
      :model-value="guide.fields.locator"
      fallback=""
      :error="guide.problems.locator ?? ''"
      :changed="false"
      @update:model-value="guide.edit('locator', $event)"
    />
  </DisclosureBox>
</template>
