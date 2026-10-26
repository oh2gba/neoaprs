// The answers of the first-run guide (composables/useSetupGuide.ts): the fields as they are typed, what is wrong with each, which steps have what they need, the place on the map they make, and the settings they change. They start as the
// daemon's settings and follow them until the user answers; the position is the latitude and the longitude (the locator of the Location control is only another way to type them).
import { computed, reactive, ref, type Ref } from "vue";
import {
  baudShown,
  degreesText,
  fieldsFrom,
  isDummy,
  KEY_OF,
  profileOf,
  setupChanges,
  stepOk,
  stepProblems,
  STEP_COUNT,
  type FieldName,
  type Problems,
  type SetupFields,
} from "@/lib/setup";
import { onEarth, parseNumber } from "@/lib/fieldcheck";

export function useSetupAnswers(values: Ref<Record<string, string>>, search: Ref<boolean | null>) {
  const fields = reactive<SetupFields>(fieldsFrom({}));
  const errors = reactive<Problems>({}); // the daemon's complaints, by field
  const touched = ref(false); // an answer was typed or picked: the settings no longer fill the answers

  const tcp = computed(() => profileOf(fields.profile)?.transport === "tcp");
  const dummy = computed(() => isDummy(fields));
  const changes = computed(() => setupChanges(fields, values.value));
  const valid = computed(() => Array.from({ length: STEP_COUNT }, (_, i) => stepOk(i, fields, search.value)));
  const problems = computed<Problems>(() => {
    const found: Problems = {};
    for (let i = 0; i < STEP_COUNT; i++) Object.assign(found, stepProblems(i, fields));
    return { ...found, ...errors };
  });
  const pin = computed(() => {
    const lat = parseNumber(fields.lat);
    const lon = parseNumber(fields.lon);
    return lat !== null && lon !== null && onEarth(lat, lon) ? { lat, lon } : null;
  });

  function clearErrors(): void {
    for (const key of Object.keys(errors)) delete errors[key as FieldName];
  }

  /** The answers are the daemon's settings. */
  function fill(now: Record<string, string>): void {
    Object.assign(fields, fieldsFrom(now));
  }

  /** The answers are the daemon's settings again, nothing answered. */
  function reset(): void {
    fill(values.value);
    clearErrors();
    touched.value = false;
  }

  /** The answer to a field, as typed; the position and the locator follow from each other. */
  function edit(field: FieldName, text: string): void {
    touched.value = true;
    fields[field] = text;
    delete errors[field];
  }

  /** The radio Find my radio found, as the settings it makes (the type, the port and the speed): the answers of the Radio step. */
  function fillRadio(found: Record<string, string>): void {
    for (const key of ["tnc/profile", "serial/port", "serial/baud"]) {
      const field = KEY_OF[key];
      const value = found[key];
      if (field !== undefined && value !== undefined) edit(field, field === "baud" ? baudShown(fields.profile, value) : value);
    }
  }

  /** A place from the map or the browser: five decimals (a metre), the longitude brought into -180 to 180. */
  function place(lat: number, lon: number): void {
    const wrapped = ((((lon + 180) % 360) + 360) % 360) - 180;
    edit("lat", degreesText(Math.round(lat * 1e5) / 1e5));
    edit("lon", degreesText(Math.round(wrapped * 1e5) / 1e5));
  }

  return { fields, errors, touched, tcp, dummy, fillRadio, changes, valid, problems, pin, fill, reset, clearErrors, edit, place };
}
