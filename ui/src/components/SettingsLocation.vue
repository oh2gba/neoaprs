<script setup lang="ts">
// Our station's place in the Station group of the Beacon tab, as a sub-section Location: the big **Pick on the map** button (Cancel while the map waits for the click) with the place in force as one readable line ("60.42945 N, 24.14524 E ·
// KP20le", "Not set"), and the latitude and longitude, behind a small "Enter coordinates" heading that is open while there is no place or one of them is wrong, else until the person opens it. A pick applies both at once (the form does that);
// typed coordinates apply together when focus leaves the pair and both are right (the fields say `commit` and the form waits for the pair).
import DisclosureBox from "@/components/DisclosureBox.vue";
import SettingsField from "@/components/SettingsField.vue";
import { positionToLocator } from "@/lib/locator";
import { parseNumber } from "@/lib/setup";
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
/** The place in force in words: degrees with N or S, E or W, and the locator; "Not set" while there is none. */
const line = computed(() => {
  const lat = number(props.current.lat);
  const lon = number(props.current.lon);
  if (lat === null || lon === null) return "Not set";
  const shown = (value: number) => String(Math.round(Math.abs(value) * 1e5) / 1e5);
  return `${shown(lat)} ${lat < 0 ? "S" : "N"}, ${shown(lon)} ${lon < 0 ? "W" : "E"} · ${positionToLocator(lat, lon)}`;
});
const open = computed(() => line.value === "Not set" || !!props.errors[LAT] || !!props.errors[LON]);
const id = (key: string) => `set-${key.replace("/", "-")}`;
</script>

<template>
  <h3 class="subgroup">Location</h3>
  <div class="location">
    <button class="btn primary location-pick" type="button" :class="{ active: picking }" @click="emit('pick')">
      {{ picking ? "Cancel" : "Pick on the map" }}
    </button>
    <span class="location-line" :class="{ muted: line === 'Not set' }">{{ line }}</span>
  </div>
  <DisclosureBox title="Enter coordinates" :open="open">
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
