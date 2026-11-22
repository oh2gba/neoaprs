<script setup lang="ts">
// Our station's place in the Station group: the Location control with the place in force as text
// and the latitude and longitude behind it. A pick applies both at once; typed coordinates or a
// locator apply together when focus leaves the pair and both are valid.
import LocationField, { type LocationPart } from "@/components/LocationField.vue";
import { placeOfText } from "@/lib/locator";

const LAT = "station/lat";
const LON = "station/lon";
defineProps<{
  /** the fields as typed */
  draft: Record<string, string>;
  /** the place in force, as text */
  current: { lat: string; lon: string };
  errors: Record<string, string>;
  changed: (key: string) => boolean;
  picking: boolean;
}>();
const emit = defineEmits<{ type: [key: string, text: string]; commit: [key: string, next: EventTarget | null]; cancel: [key: string]; pick: [] }>();

/**
 * The key a part of the control is about: the locator is typed as both coordinates, sent together.
 */
const keyOf = (part: LocationPart): string => (part === "lon" ? LON : LAT);
/** Esc in a field restores its value; in the locator, both coordinates. */
function cancel(part: LocationPart): void {
  if (part === "locator") emit("cancel", LON);
  emit("cancel", keyOf(part));
}
</script>

<template>
  <LocationField
    id="set-station"
    :place="placeOfText(current.lat, current.lon)"
    :picking="picking"
    :lat="draft[LAT] ?? ''"
    :lon="draft[LON] ?? ''"
    :errors="{ lat: errors[LAT], lon: errors[LON] }"
    :changed="{ lat: changed(LAT), lon: changed(LON) }"
    apply
    @pick="emit('pick')"
    @update:lat="emit('type', LAT, $event)"
    @update:lon="emit('type', LON, $event)"
    @commit="(part, next) => emit('commit', keyOf(part), next)"
    @cancel="cancel"
  />
</template>
