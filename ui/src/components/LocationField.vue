<script setup lang="ts">
// The one control for a place, used by My station, the Objects form and the setup guide's
// position step: the row Location with **Choose on map** and the place in force as text. The
// text is a button that opens an entry for latitude and longitude and a 6-character Maidenhead
// locator (lib/locator.ts), each following the other; the entry opens by itself when a
// coordinate is wrong. `alwaysOpen` (setup guide) keeps it open. `apply` (My station) makes
// Enter and leaving a field emit `commit` and Esc emit `cancel`. The typed locator is kept as
// typed while it names the place the coordinates hold.
import { computed, nextTick, ref, useId, watch } from "vue";
import SettingsField from "@/components/SettingsField.vue";
import { t } from "@/i18n";
import { parseNumber } from "@/lib/fieldcheck";
import { locatorOfText, locatorProblem, locatorToPosition } from "@/lib/locator";
import { degreesText } from "@/lib/setup";

export type LocationPart = "lat" | "lon" | "locator";

const props = withDefaults(
  defineProps<{
    /** the base of the ids of the three fields (`${id}-lat`, `${id}-lon`, `${id}-locator`) */
    id: string;
    /** the place in force in words (lib/locator.ts placeLine); null while there is none */
    place: string | null;
    /** the map waits for a click: the button says Cancel */
    picking: boolean;
    /** the latitude and the longitude as they are typed */
    lat: string;
    lon: string;
    /** what is wrong with each, by part */
    errors?: Partial<Record<"lat" | "lon", string>>;
    /** a coordinate holds an unapplied change (when the form applies as it is changed), by part */
    changed?: Partial<Record<"lat" | "lon", boolean>>;
    /** the fields apply as changed: Enter or leaving them emits `commit`, Esc emits `cancel` */
    apply?: boolean;
    /** the entry stays open and the place is plain text (setup guide); else it opens on a click
     * or a wrong coordinate */
    alwaysOpen?: boolean;
  }>(),
  { errors: () => ({}), changed: () => ({}), apply: false, alwaysOpen: false },
);
const emit = defineEmits<{
  pick: [];
  "update:lat": [text: string];
  "update:lon": [text: string];
  commit: [part: LocationPart, next: EventTarget | null];
  cancel: [part: LocationPart];
}>();

const label = useId();
const entry = `${props.id}-entry`;
const wrong = computed(() => !!props.errors.lat || !!props.errors.lon);
const needed = () => wrong.value || props.alwaysOpen;
/** Whether the entry is open: closed at first, open on a wrong coordinate or in the guide. */
const entering = ref(needed());
watch(needed, (now) => {
  if (now) entering.value = true;
});

/** The fields' words, built at render time so that they follow the language. */
const degrees = (part: "lat" | "lon") => ({
  label: t(part === "lat" ? "settings.lat.label" : "settings.lon.label"),
  unit: "°",
  empty: part === "lat" ? "60.17" : "24.94",
});
const locatorInfo = () => ({ label: t("settings.locator.label"), empty: "KP20le" });

/** The locator as typed; null while the field shows the one derived from the coordinates. */
const typed = ref<string | null>(null);
const derived = computed(() => locatorOfText(props.lat, props.lon));
const shown = computed(() => typed.value ?? derived.value);
/** The typed locator names the place the coordinates hold. */
function names(text: string): boolean {
  const at = locatorToPosition(text);
  return at !== null && parseNumber(props.lat) === at.lat && parseNumber(props.lon) === at.lon;
}
// rewrite the locator when a change did not come from the typed locator
watch(derived, () => {
  if (typed.value !== null && !names(typed.value)) typed.value = null;
});
const locatorError = computed(() => (typed.value === null ? "" : locatorProblem(typed.value)));
/** Whether the locator holds an unapplied change: typed differently from the coordinates, or
 * rewritten from them. */
const locatorChanged = computed(
  () =>
    !!props.changed.lat ||
    !!props.changed.lon ||
    (typed.value !== null && typed.value.trim().toUpperCase() !== derived.value.toUpperCase()),
);

function typeLocator(text: string): void {
  typed.value = text;
  const at = locatorToPosition(text);
  if (at === null) return;
  emit("update:lat", degreesText(at.lat));
  emit("update:lon", degreesText(at.lon));
}

function commitLocator(next: EventTarget | null): void {
  if (typed.value !== null && (typed.value.trim() === "" || locatorToPosition(typed.value) !== null))
    typed.value = null;
  emit("commit", "locator", next);
}

function cancelLocator(): void {
  typed.value = null;
  emit("cancel", "locator");
}

const root = ref<HTMLElement | null>(null);
/** A click on the place opens or closes the entry; opening focuses the latitude field. */
async function toggle(): Promise<void> {
  entering.value = !entering.value;
  if (!entering.value) return;
  await nextTick();
  root.value?.querySelector<HTMLInputElement>(`input[id="${props.id}-lat"]`)?.focus();
}
</script>

<template>
  <div ref="root" class="field location-field" role="group" :aria-labelledby="label">
    <span :id="label" class="field-label">{{ t("settings.location.heading") }}</span>
    <div class="field-control location-control">
      <button
        class="btn location-pick"
        type="button"
        :class="{ active: picking }"
        :aria-pressed="picking"
        @click="emit('pick')"
      >
        {{ picking ? t("settings.location.cancel") : t("settings.location.pick") }}
      </button>
      <span v-if="alwaysOpen" :id="`${id}-place`" class="location-shown" :class="{ muted: place === null }">{{
        place ?? t("settings.location.not_set")
      }}</span>
      <button
        v-else
        :id="`${id}-place`"
        class="location-place"
        type="button"
        :class="{ muted: place === null }"
        :aria-expanded="entering"
        :aria-controls="entry"
        :title="t('settings.location.edit')"
        @click="toggle"
      >
        {{ place ?? t("settings.location.not_set") }}
      </button>
    </div>
    <div v-if="entering" :id="entry" class="location-entry" role="group" :aria-label="t('settings.location.entry')">
      <SettingsField
        :id="`${id}-lat`"
        :info="degrees('lat')"
        :model-value="lat"
        fallback=""
        :error="errors.lat ?? ''"
        :changed="changed.lat ?? false"
        :apply="apply"
        @update:model-value="emit('update:lat', $event)"
        @commit="emit('commit', 'lat', $event)"
        @cancel="emit('cancel', 'lat')"
      />
      <SettingsField
        :id="`${id}-lon`"
        :info="degrees('lon')"
        :model-value="lon"
        fallback=""
        :error="errors.lon ?? ''"
        :changed="changed.lon ?? false"
        :apply="apply"
        @update:model-value="emit('update:lon', $event)"
        @commit="emit('commit', 'lon', $event)"
        @cancel="emit('cancel', 'lon')"
      />
      <SettingsField
        :id="`${id}-locator`"
        :info="locatorInfo()"
        :model-value="shown"
        fallback=""
        :error="locatorError"
        :changed="locatorChanged"
        :apply="apply"
        @update:model-value="typeLocator"
        @commit="commitLocator"
        @cancel="cancelLocator"
      />
    </div>
  </div>
</template>
