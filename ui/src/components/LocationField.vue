<script setup lang="ts">
// The row "Location" of a form, in the look of the row of the Call above it (the label bold in the label column) with, in the input column: the button that chooses the place on the map (Cancel while the map waits for the click), the place in
// force as one readable line ("60.42945 N, 24.14524 E · KP20bk", "Not set") and a small heading "Enter coordinates" that opens the fields of the slot; it is open while `open` is true (no place, or a coordinate is wrong), else until the
// person opens it. The Beacon tab (components/SettingsLocation.vue) and the Objects form (components/ObjectForm.vue) are made of this; the setup guide's step has its own, larger look.
import { useId } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import { t } from "@/i18n";

defineProps<{
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
    <span :id="label" class="field-label">{{ t("settings.location.heading") }}</span>
    <div class="field-control location-control">
      <button class="btn primary location-pick" type="button" :class="{ active: picking }" :aria-pressed="picking" @click="emit('pick')">
        {{ picking ? t("settings.location.cancel") : t("settings.location.pick") }}
      </button>
      <span class="location-line" :class="{ muted: place === null }">{{ place ?? t("settings.location.not_set") }}</span>
      <DisclosureBox :title="t('settings.location.enter')" :open="open"><slot /></DisclosureBox>
    </div>
  </div>
</template>
