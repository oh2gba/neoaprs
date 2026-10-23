<script setup lang="ts">
// Our station's place in the Station group of the Beacon tab, as a sub-section Location: the big **Pick on the map** button (Cancel while the map waits for the click) with the place in force as one readable line ("60.42945 N, 24.14524 E ·
// KP20le", "Not set"), and the latitude and longitude, behind a small "Enter coordinates" heading that is open while there is no place or one of them is wrong, else until the person opens it. A pick applies both at once (the form does that);
// typed coordinates apply together when focus leaves the pair and both are right (the fields say `commit` and the form waits for the pair).
import DisclosureBox from "@/components/DisclosureBox.vue";
import SettingsField from "@/components/SettingsField.vue";
import { t } from "@/i18n";
import { positionToLocator } from "@/lib/locator";
import { parseNumber } from "@/lib/fieldcheck";
import { FIELDS } from "@/lib/settings";
import { computed } from "vue";

const LAT = "station/lat";
const LON = "station/lon";
const props = defineProps<{
  /** the fields as typed */
  draft: Record<string, string>;
  /** the place in force, as text */
  current: { lat: string; lon: string };
  errors: Record<string, string>;
  changed: (key: string) => boolean;
  picking: boolean;
}>();
const emit = defineEmits<{ type: [key: string, text: string]; commit: [key: string, next: EventTarget | null]; cancel: [key: string]; pick: [] }>();

const number = (value: string) => parseNumber(value);
/** The place in force in words: degrees with N or S, E or W, and the locator; null while there is none. */
const place = computed(() => {
  const lat = number(props.current.lat);
  const lon = number(props.current.lon);
  if (lat === null || lon === null) return null;
  const shown = (value: number) => String(Math.round(Math.abs(value) * 1e5) / 1e5);
  return `${shown(lat)} ${lat < 0 ? "S" : "N"}, ${shown(lon)} ${lon < 0 ? "W" : "E"} · ${positionToLocator(lat, lon)}`;
});
const open = computed(() => place.value === null || !!props.errors[LAT] || !!props.errors[LON]);
const id = (key: string) => `set-${key.replace("/", "-")}`;
</script>

<template>
  <h3 class="subgroup">{{ t("settings.location.heading") }}</h3>
  <div class="location">
    <button class="btn primary location-pick" type="button" :class="{ active: picking }" @click="emit('pick')">
      {{ picking ? t("settings.location.cancel") : t("settings.location.pick") }}
    </button>
    <span class="location-line" :class="{ muted: place === null }">{{ place ?? t("settings.location.not_set") }}</span>
  </div>
  <DisclosureBox :title="t('settings.location.enter')" :open="open">
    <SettingsField
      v-for="key in [LAT, LON]"
      :id="id(key)"
      :key="key"
      :info="FIELDS[key] ?? { label: key }"
      :model-value="draft[key] ?? ''"
      fallback=""
      :error="errors[key] ?? ''"
      :changed="changed(key)"
      :apply="true"
      @update:model-value="emit('type', key, $event)"
      @commit="emit('commit', key, $event)"
      @cancel="emit('cancel', key)"
    />
  </DisclosureBox>
</template>
