<script setup lang="ts">
// The one control for a place, the same in the My station tab (components/SettingsLocation.vue), the Objects form (components/ObjectForm.vue) and the first-run guide's position step (components/SetupPosition.vue): the row Location with, in the input column, the plain button
// **Choose on map** (Cancel while the map waits for the click) and, beside it on the same line, the place in force as text ("60.42944 N, 24.14524 E · KP20bk", "Not set"). On a narrow panel the text wraps under the button, never cut off. The text is a button too:
// a click opens the entry under the row, which has two ways to give the place, the latitude and longitude, and a Maidenhead locator (6 characters: the centre of its square; lib/locator.ts), each following the other. The entry is closed until the person clicks the place ("Not set" is still the thing to click) and opens by itself when a coordinate is
// wrong. The first-run guide's position step gives `alwaysOpen`: the entry is what the step asks for, so it is open the whole time and the place is plain text, nothing to click. A form that applies as it is changed (the My station tab) gives `apply`: Enter and leaving a field say `commit` (with where focus went and which field), Esc says `cancel`, as the fields of that form do.
// The locator is kept here, as typed, while it names the place the coordinates hold; any other change of the coordinates writes it again.
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
    /** a coordinate holds a change that is not applied yet (the form applies as it is changed), by part */
    changed?: Partial<Record<"lat" | "lon", boolean>>;
    /** the fields apply as they are changed: Enter and leaving them say `commit`, Esc says `cancel` */
    apply?: boolean;
    /** the entry is open the whole time and the place is plain text (the first-run guide's position step), else it opens on a click or a wrong coordinate */
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
/** The entry is open: closed from the start, open when a coordinate is wrong (the guide's the whole time), then as the person leaves it. */
const entering = ref(needed());
watch(needed, (now) => {
  if (now) entering.value = true;
});

/** The fields' own words, made when the page is drawn so that they follow the language. */
const degrees = (part: "lat" | "lon") => ({
  label: t(part === "lat" ? "settings.lat.label" : "settings.lon.label"),
  unit: "°",
  empty: part === "lat" ? "60.17" : "24.94",
});
const locatorInfo = () => ({ label: t("settings.locator.label"), empty: "KP20le" });

/** The locator as it was typed, null while the field shows the one of the coordinates. */
const typed = ref<string | null>(null);
const derived = computed(() => locatorOfText(props.lat, props.lon));
const shown = computed(() => typed.value ?? derived.value);
/** The typed locator names the place the coordinates hold. */
function names(text: string): boolean {
  const at = locatorToPosition(text);
  return at !== null && parseNumber(props.lat) === at.lat && parseNumber(props.lon) === at.lon;
}
// a change of the coordinates that the typed locator did not make writes the locator again
watch(derived, () => {
  if (typed.value !== null && !names(typed.value)) typed.value = null;
});
const locatorError = computed(() => (typed.value === null ? "" : locatorProblem(typed.value)));
/** The locator holds a change when it was typed as something else than the coordinates say, or when the coordinates do (it is written from them). */
const locatorChanged = computed(
  () => !!props.changed.lat || !!props.changed.lon || (typed.value !== null && typed.value.trim().toUpperCase() !== derived.value.toUpperCase()),
);

function typeLocator(text: string): void {
  typed.value = text;
  const at = locatorToPosition(text);
  if (at === null) return;
  emit("update:lat", degreesText(at.lat));
  emit("update:lon", degreesText(at.lon));
}

function commitLocator(next: EventTarget | null): void {
  if (typed.value !== null && (typed.value.trim() === "" || locatorToPosition(typed.value) !== null)) typed.value = null;
  emit("commit", "locator", next);
}

function cancelLocator(): void {
  typed.value = null;
  emit("cancel", "locator");
}

const root = ref<HTMLElement | null>(null);
/** A click on the place opens or closes the entry; an opened one takes the focus (the first field, the latitude). */
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
      <button class="btn location-pick" type="button" :class="{ active: picking }" :aria-pressed="picking" @click="emit('pick')">
        {{ picking ? t("settings.location.cancel") : t("settings.location.pick") }}
      </button>
      <span v-if="alwaysOpen" :id="`${id}-place`" class="location-shown" :class="{ muted: place === null }">{{ place ?? t("settings.location.not_set") }}</span>
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
