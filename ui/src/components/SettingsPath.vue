<script setup lang="ts">
// The beacon's path as one choice: Recommended (the empty setting; the path of the station's symbol, WIDE1-1,WIDE2-1 for a moving station and WIDE2-2 for a fixed one: the `recommended` the form works out), Direct only (no digipeaters) and Custom, which shows a field for the calls. Recommended and Direct only apply at once (`choose`);
// the custom calls apply on Enter or when the field is left (`commit`), and Esc (`cancel`) puts the path in force back. A path that is neither of the first two (WIDE2-2) shows as Custom with its calls in the field. An empty custom
// field is the recommended path again. The path builder's button (PathBuilder) beside the choice builds a path from the one in force, held to the setting's rule; Use applies it at once, as a choice does (DIRECT is Direct only).
// With the radios: a Path row for each radio that is on and may carry a path (lib/beaconstatus.ts `pathRows`), each named while several radios are on ("FM: path") and each the radio's own setting (`radio/<id>/path`; radio 1's
// is `beacon/path` while the settings of before are there), worked on the page's settings as the form works its fields. A station with one radio has the one row of the props, as it had; so has a page with no context.
import { computed, inject, ref, watch } from "vue";
import PathBuilder from "@/components/PathBuilder.vue";
import SettingsField from "@/components/SettingsField.vue";
import { DAEMON_KEY } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { t } from "@/i18n";
import { followRadioValues, pathRows, radioValueOf } from "@/lib/beaconstatus";
import { DIRECT, callListText } from "@/lib/calls";
import { problemOf } from "@/lib/fieldcheck";
import { fieldId } from "@/lib/radios";
import type { Choice } from "@/lib/settingchoices";
import type { FieldInfo } from "@/lib/settings";

const props = defineProps<{
  id: string;
  info: FieldInfo;
  modelValue: string;
  error: string;
  changed: boolean;
  recommended: string;
  disabled?: boolean;
  /** one radio's row of the rows this component draws for the radios: drawn as it is, with no rows of its own */
  row?: boolean;
}>();
const emit = defineEmits<{ "update:modelValue": [value: string]; choose: [value: string]; commit: [next: EventTarget | null]; cancel: [] }>();

const page = inject(DAEMON_KEY, null);
const radios = useRadios();
/** The rows of the radios; null for the one row of the props. */
const rows = computed(() => (props.row || page === null ? null : pathRows(radios.enabled.value)));
const settings = page?.settings;
const inForce = (key: string): string => radioValueOf(page?.config.value ?? null, key) ?? "";
const valueOf = (key: string): string => settings?.draft[key] ?? inForce(key);
const changedOf = (key: string): boolean => settings !== undefined && valueOf(key) !== (key in settings.values.value ? settings.expected(key) : inForce(key));
const infoOf = (name: string | null): FieldInfo => (name === null ? props.info : { ...props.info, label: t("settings.path.on_radio", { name }) });
const idOf = (key: string): string => (key === "beacon/path" ? props.id : `set-${fieldId(key)}`);
// a radio's path that the settings do not hold yet follows the daemon, as their own keys do
watch(
  () => Object.fromEntries((rows.value ?? []).map((one) => [one.key, inForce(one.key)])),
  (now, before) => settings && followRadioValues(settings.draft, settings.values.value, now, before),
);
/** A radio's typed path is checked as the beacon's is (the setting's rule), and sent. */
function commitRow(key: string): void {
  if (settings === undefined) return;
  const problem = problemOf("beacon/path", settings.draft[key] ?? "");
  if (key !== "beacon/path" && problem !== "") settings.errors[key] = problem;
  else settings.commit([key]);
}
function cancelRow(key: string): void {
  if (settings === undefined) return;
  settings.cancel(key);
  if (!(key in settings.values.value) && !settings.saving.value) settings.draft[key] = inForce(key);
}

const RECOMMENDED_CHOICE = "recommended";
const DIRECT_CHOICE = "direct";
const CUSTOM_CHOICE = "custom";

/** Which of the three the setting as it stands is. */
const kind = computed(() => {
  const text = callListText(props.modelValue);
  return text === "" ? RECOMMENDED_CHOICE : text === DIRECT ? DIRECT_CHOICE : CUSTOM_CHOICE;
});
const typing = ref(kind.value === CUSTOM_CHOICE);
/** The field was changed since Custom was picked: leaving it unchanged sends nothing. */
const edited = ref(false);
const shown = computed(() => (typing.value ? CUSTOM_CHOICE : kind.value));
/** The calls the field starts with: the path in force when it is custom, else the recommended one to edit from. */
const start = computed(() => (kind.value === CUSTOM_CHOICE ? props.modelValue : props.recommended));
const text = ref(start.value);

const choices = computed<Choice[]>(() => [
  { value: RECOMMENDED_CHOICE, label: t("settings.path.recommended", { path: props.recommended }) },
  { value: DIRECT_CHOICE, label: t("settings.path.direct") },
  { value: CUSTOM_CHOICE, label: t("settings.path.custom") },
]);
const field = computed<FieldInfo>(() => ({ ...props.info, kind: "choice", choices: choices.value }));

// the path in force changes (the daemon took a choice, another page changed it): the field follows, unless the calls are being typed
watch(
  () => props.modelValue,
  () => {
    if (edited.value) return;
    typing.value = kind.value === CUSTOM_CHOICE;
    text.value = start.value;
  },
);

function pick(value: string): void {
  if (value === CUSTOM_CHOICE) {
    typing.value = true;
    edited.value = false;
    text.value = start.value;
    return;
  }
  typing.value = false;
  edited.value = false;
  emit("choose", value === DIRECT_CHOICE ? DIRECT : "");
}

/** The path built in the path builder, applied at once. */
function build(path: string): void {
  edited.value = false;
  emit("choose", path);
}

function type(event: Event): void {
  if (!(event.target instanceof HTMLInputElement)) return;
  edited.value = true;
  text.value = event.target.value;
  emit("update:modelValue", event.target.value);
}

function leave(event: FocusEvent): void {
  if (edited.value) emit("commit", event.relatedTarget);
  else typing.value = kind.value === CUSTOM_CHOICE;
  edited.value = false;
}

function enter(): void {
  if (edited.value) emit("commit", null);
  edited.value = false;
}

function escape(event: KeyboardEvent): void {
  event.stopPropagation();
  if (edited.value) emit("cancel");
  edited.value = false;
  typing.value = kind.value === CUSTOM_CHOICE;
  text.value = start.value;
}

// a path the daemon refused stays in the field it was typed in
watch(
  () => props.error,
  (now) => {
    if (now !== "" && props.changed) {
      typing.value = true;
      edited.value = true;
    }
  },
);
</script>

<template>
  <template v-if="rows !== null && settings !== undefined">
    <SettingsPath
      v-for="one in rows"
      :id="idOf(one.key)"
      :key="one.key"
      row
      :info="infoOf(one.name)"
      :model-value="valueOf(one.key)"
      :error="settings.errors[one.key] ?? ''"
      :changed="changedOf(one.key)"
      :recommended="recommended"
      :disabled="disabled"
      @update:model-value="settings.edit(one.key, $event)"
      @choose="settings.change({ [one.key]: $event })"
      @commit="commitRow(one.key)"
      @cancel="cancelRow(one.key)"
    />
  </template>
  <SettingsField
    v-else
    :id="id"
    :info="field"
    :model-value="shown"
    fallback=""
    :error="error"
    :changed="changed"
    :disabled="disabled"
    @update:model-value="pick"
  >
    <template #after>
      <input
        v-if="typing"
        :id="`${id}-typed`"
        class="input mono"
        type="text"
        autocomplete="off"
        spellcheck="false"
        :value="text"
        :disabled="disabled"
        :placeholder="recommended"
        :aria-label="t('settings.path.custom_label')"
        @input="type"
        @blur="leave"
        @keydown.enter.prevent="enter"
        @keydown.esc="escape"
      />
      <PathBuilder :value="modelValue" :usual="recommended" :check="(text) => problemOf('beacon/path', text)" :disabled="disabled" @use="build" />
    </template>
  </SettingsField>
</template>
