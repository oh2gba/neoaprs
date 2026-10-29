<script setup lang="ts">
// The beacon's path as one choice: Recommended (the empty setting; the path of the station's symbol, WIDE1-1,WIDE2-1 for a moving station and WIDE2-1 for a fixed one: the `recommended` the form works out), Direct only (no digipeaters) and Custom, which shows a field for the calls. Recommended and Direct only apply at once (`choose`);
// the custom calls apply on Enter or when the field is left (`commit`), and Esc (`cancel`) puts the path in force back. A path that is neither of the first two (WIDE2-2) shows as Custom with its calls in the field. An empty custom
// field is the recommended path again. The path builder's button (PathBuilder) beside the choice builds a path from the one in force, held to the setting's rule; Use applies it at once, as a choice does (DIRECT is Direct only).
import { computed, ref, watch } from "vue";
import PathBuilder from "@/components/PathBuilder.vue";
import SettingsField from "@/components/SettingsField.vue";
import { t } from "@/i18n";
import { DIRECT, callListText } from "@/lib/calls";
import { problemOf } from "@/lib/fieldcheck";
import type { Choice } from "@/lib/settingchoices";
import type { FieldInfo } from "@/lib/settings";

const props = defineProps<{ id: string; info: FieldInfo; modelValue: string; error: string; changed: boolean; recommended: string; disabled?: boolean }>();
const emit = defineEmits<{ "update:modelValue": [value: string]; choose: [value: string]; commit: [next: EventTarget | null]; cancel: [] }>();

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
  <SettingsField :id="id" :info="field" :model-value="shown" fallback="" :error="error" :changed="changed" :disabled="disabled" @update:model-value="pick">
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
