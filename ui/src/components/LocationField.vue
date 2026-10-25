<script setup lang="ts">
// The row "Location" of a form, in the look of the row of the Call above it (the label bold in the label column) with, in the input column: the button that chooses the place on the map (Cancel while the map waits for the click), the place in
// force as one readable line ("60.42945 N, 24.14524 E · KP20bk", "Not set") and a small heading "Enter coordinates" that opens the fields of the slot; it is open while `open` is true (no place, or a coordinate is wrong), else until the
// person opens it. With `home` (the beacon follows a GPS) the row is called Home position and a note says the GPS position is what is sent. The Beacon tab (components/SettingsLocation.vue) and the Objects form (components/ObjectForm.vue) are made of this; the setup guide's step has its own, larger look.
import { useId } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import { t } from "@/i18n";

defineProps<{
  /** the beacon follows a GPS: this place is only the home position, said so in the label and under the line */
  home?: boolean;
  /** the place in words (lib/locator.ts placeLine); null while there is none */
  place: string | null;
  /** the map waits for a click: the button says Cancel */
  picking: boolean;
  /** the coordinates are open: there is no place, or a coordinate is wrong */
  open: boolean;
}>();
const emit = defineEmits<{ pick: [] }>();
const label = useId();
</script>

<template>
  <div class="field location-field" role="group" :aria-labelledby="label">
    <span :id="label" class="field-label">{{ home ? t("settings.location.home") : t("settings.location.heading") }}</span>
    <div class="field-control location-control">
      <button class="btn primary location-pick" type="button" :class="{ active: picking }" :aria-pressed="picking" @click="emit('pick')">
        {{ picking ? t("settings.location.cancel") : t("settings.location.pick") }}
      </button>
      <span class="location-line" :class="{ muted: place === null }">{{ place ?? t("settings.location.not_set") }}</span>
      <span v-if="home" class="location-note muted">{{ t("settings.location.home_note") }}</span>
      <DisclosureBox :title="t('settings.location.enter')" :open="open"><slot /></DisclosureBox>
    </div>
  </div>
</template>
