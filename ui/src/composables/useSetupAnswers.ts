// The answers of the first-run guide: the typed fields, the daemon's complaints, which steps have
// what they need, the place on the map and the settings they change. They start as the daemon's
// settings and follow them until the user answers. The position is latitude and longitude; the
// locator is another way to type them. The Radio step has no answers (see SetupRadio).
import { computed, reactive, ref, type Ref } from "vue";
import {
  degreesText,
  fieldsFrom,
  roundPlace,
  setupChanges,
  stepOk,
  stepProblems,
  STEP_COUNT,
  wrapLongitude,
  type FieldName,
  type Problems,
  type SetupFields,
} from "@/lib/setup";
import { onEarth, parseNumber } from "@/lib/fieldcheck";

export function useSetupAnswers(values: Ref<Record<string, string>>) {
  const fields = reactive<SetupFields>(fieldsFrom({}));
  const errors = reactive<Problems>({});
  // An answer was typed or picked: the settings do not fill the answers any more.
  const touched = ref(false);

  const changes = computed(() => setupChanges(fields, values.value));
  const valid = computed(() => Array.from({ length: STEP_COUNT }, (_, i) => stepOk(i, fields)));
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

  function fill(now: Record<string, string>): void {
    Object.assign(fields, fieldsFrom(now));
  }

  function reset(): void {
    fill(values.value);
    clearErrors();
    touched.value = false;
  }

  /** Set a field as typed; the position and the locator follow from each other. */
  function edit(field: FieldName, text: string): void {
    touched.value = true;
    fields[field] = text;
    delete errors[field];
  }

  /** A place from the map or the browser: five decimals, longitude brought into -180 to 180. */
  function place(lat: number, lon: number): void {
    edit("lat", degreesText(roundPlace(lat)));
    edit("lon", degreesText(wrapLongitude(lon)));
  }

  return { fields, errors, touched, changes, valid, problems, pin, fill, reset, clearErrors, edit, place };
}
