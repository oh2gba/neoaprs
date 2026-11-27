<script setup lang="ts">
// The beacon's path as one choice: Recommended (the empty setting; the symbol's path, `recommended`
// from the form), Direct only, and Custom with a field for calls. Recommended and Direct only apply
// at once (`choose`); custom calls apply on Enter or blur (`commit`), Esc (`cancel`) restores the
// path in force. A path that is neither of the first two shows as Custom. An empty custom field is
// Recommended again. The PathBuilder button builds from the path in force; Use applies it at once.
// With radios: one Path row per radio that is on and may carry a path (lib/beaconstatus.ts
// `pathRows`), each radio's own setting (`radio/<id>/path`); its Recommended is the path that radio
// really takes while its own is empty. Without context there is one row from the props.
import { computed, inject, ref, watch } from "vue";
import PathBuilder from "@/components/PathBuilder.vue";
import SettingsField from "@/components/SettingsField.vue";
import { DAEMON_KEY } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { t } from "@/i18n";
import { pathRows, radioValueOf } from "@/lib/beaconstatus";
import { DIRECT, callListText } from "@/lib/calls";
import { problemOf } from "@/lib/fieldcheck";
import { confirms } from "@/lib/ime";
import { fieldId, recommendedFor } from "@/lib/radios";
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
  /** one radio's row of the rows drawn for the radios: drawn as it is, with no rows of its own */
  row?: boolean;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: string];
  choose: [value: string];
  commit: [next: EventTarget | null];
  cancel: [];
}>();

const page = inject(DAEMON_KEY, null);
const radios = useRadios();
/** The rows of the radios; null for the one row of the props. */
const rows = computed(() => (props.row || page === null ? null : pathRows(radios.enabled.value)));
const settings = page?.settings;
const inForce = (key: string): string => radioValueOf(page?.config.value ?? null, key) ?? "";
const valueOf = (key: string): string => settings?.draft[key] ?? inForce(key);
const changedOf = (key: string): boolean => settings !== undefined && valueOf(key) !== settings.expected(key);
const infoOf = (name: string | null): FieldInfo =>
  name === null ? props.info : { ...props.info, label: t("settings.path.on_radio", { name }) };
const idOf = (key: string): string => `set-${fieldId(key)}`;
/**
 * What a radio's Recommended is: its type's path (LoRa WIDE1-1), else the symbol's: what the daemon
 * sends while its own path is empty.
 */
const recommendedOf = (id: number): string => {
  const radio = radios.byId(id);
  return radio === undefined ? props.recommended : recommendedFor(radio, props.recommended);
};
/** A radio's typed path is checked as the beacon's is, and sent. */
function commitRow(key: string): void {
  if (settings === undefined) return;
  const problem = problemOf("beacon/path", settings.draft[key] ?? "");
  if (problem !== "") settings.errors[key] = problem;
  else settings.commit([key]);
}
function cancelRow(key: string): void {
  if (settings === undefined) return;
  settings.cancel(key);
}

const RECOMMENDED_CHOICE = "recommended";
const DIRECT_CHOICE = "direct";
const CUSTOM_CHOICE = "custom";

/** Which of the three choices the setting stands at. */
const kind = computed(() => {
  const text = callListText(props.modelValue);
  return text === "" ? RECOMMENDED_CHOICE : text === DIRECT ? DIRECT_CHOICE : CUSTOM_CHOICE;
});
const typing = ref(kind.value === CUSTOM_CHOICE);
/** The field was changed since Custom was picked: leaving it unchanged sends nothing. */
const edited = ref(false);
const shown = computed(() => (typing.value ? CUSTOM_CHOICE : kind.value));
/**
 * The calls the field starts with: the path in force when custom, else the recommended one to edit
 * from.
 */
const start = computed(() => (kind.value === CUSTOM_CHOICE ? props.modelValue : props.recommended));
const text = ref(start.value);

const choices = computed<Choice[]>(() => [
  { value: RECOMMENDED_CHOICE, label: t("settings.path.recommended", { path: props.recommended }) },
  { value: DIRECT_CHOICE, label: t("settings.path.direct") },
  { value: CUSTOM_CHOICE, label: t("settings.path.custom") },
]);
const field = computed<FieldInfo>(() => ({ ...props.info, kind: "choice", choices: choices.value }));

// the path in force changes (the daemon took a choice, another page changed it): the field follows
// unless being typed in
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

function enter(event: KeyboardEvent): void {
  if (!confirms(event)) return;
  event.preventDefault();
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

// a path the daemon refused stays in the field
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
      :recommended="recommendedOf(one.radio)"
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
    class="pathfield"
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
        @keydown.enter="enter"
        @keydown.esc="escape"
      />
      <PathBuilder
        :value="modelValue"
        :usual="recommended"
        :check="(text) => problemOf('beacon/path', text)"
        :disabled="disabled"
        @use="build"
      />
    </template>
  </SettingsField>
</template>
