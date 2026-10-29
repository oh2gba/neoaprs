<script setup lang="ts">
// One setting: its label, the input (a checkbox for a yes/no setting, a choice for a short list, the call with its SSID dropdown, read-only for one the daemon writes), the default as the placeholder, a unit after it, the daemon's complaint under it, and a slot after it for a button. What it says of itself: `update:modelValue` with the text as it is typed (and for a choice), `choose`
// when a choice is made (a list, a switch), `commit` when a typed field is finished with Enter or left (with the element focus went to), `cancel` for Esc in a field that holds a change or a complaint.
// A `hint` is a quiet line under the field (advice, never a block). A `disabled` field is shown greyed with its value, as the My station tab shows what belongs to a beacon that is Off. A field whose meaning a non-developer may not know has a small (i) after it (`info.tip`); nothing else explains it, and the one thing a word cannot say is the `title` of the field.
import { computed } from "vue";
import CallInput from "@/components/CallInput.vue";
import InfoTip from "@/components/InfoTip.vue";
import { t } from "@/i18n";
import type { Choice } from "@/lib/settingchoices";
import type { FieldInfo } from "@/lib/settings";

const props = defineProps<{
  id: string;
  info: FieldInfo;
  modelValue: string;
  fallback: string;
  error: string;
  changed: boolean;
  /** the field applies as it is changed (the settings form): Enter and leaving it say `commit`, Esc says `cancel`; else it is a field of a form with a button (the setup guide), where Enter submits */
  apply?: boolean;
  /** greyed out: the control and its label are dimmed and cannot be changed, the value is kept (the (i) still opens) */
  disabled?: boolean;
  /** a quiet line under the field that advises and blocks nothing (the frequency of the status text); the complaint of the daemon takes its place */
  hint?: string;
}>();
const emit = defineEmits<{ "update:modelValue": [value: string]; choose: [value: string]; commit: [next: EventTarget | null]; cancel: [] }>();

const errorId = computed(() => `${props.id}-error`);
const describedBy = computed(() => (props.error ? errorId.value : undefined));
const placeholder = computed(() => props.info.empty ?? (props.fallback !== "" ? props.fallback : t("settings.default_placeholder")));

/** The options of a choice: the words for each value, and the value in force when it is none of them (a setting changed from the shell). */
const options = computed<Choice[]>(() => {
  const listed = (props.info.choices ?? []).map((c) => (typeof c === "string" ? { value: c, label: c } : c));
  return props.modelValue === "" || listed.some((c) => c.value === props.modelValue)
    ? listed
    : [...listed, { value: props.modelValue, label: props.info.other?.(props.modelValue) ?? props.modelValue }];
});

function onInput(event: Event): void {
  const target = event.target;
  const choice = target instanceof HTMLSelectElement || (target instanceof HTMLInputElement && target.type === "checkbox");
  const value =
    target instanceof HTMLInputElement && target.type === "checkbox"
      ? target.checked
        ? "true"
        : "false"
      : target instanceof HTMLInputElement || target instanceof HTMLSelectElement
        ? target.value
        : null;
  if (value === null) return;
  emit("update:modelValue", value);
  if (choice) emit("choose", value);
}

function onEnter(event: KeyboardEvent): void {
  if (!props.apply) return;
  event.preventDefault();
  emit("commit", null);
}

function onEscape(event: KeyboardEvent): void {
  if (!props.apply || (!props.changed && props.error === "")) return;
  event.stopPropagation();
  emit("cancel");
}
</script>

<template>
  <div class="field" :class="{ changed, invalid: error !== '', disabled }" :title="info.title">
    <label :for="id">{{ info.label }}</label>
    <div class="field-control">
      <input
        v-if="info.kind === 'bool'"
        :id="id"
        class="check"
        type="checkbox"
        :checked="modelValue === 'true'"
        :disabled="disabled"
        :aria-describedby="describedBy"
        @change="onInput"
      />
      <select
        v-else-if="info.kind === 'choice'"
        :id="id"
        class="input"
        :value="modelValue"
        :disabled="disabled"
        :aria-describedby="describedBy"
        @change="onInput"
      >
        <option v-for="choice in options" :key="choice.value" :value="choice.value">{{ choice.label }}</option>
      </select>
      <CallInput
        v-else-if="info.kind === 'call'"
        :id="id"
        :model-value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :invalid="error !== ''"
        :describedby="describedBy"
        @update:model-value="emit('update:modelValue', $event)"
        @choose="emit('choose', $event)"
        @blur="apply && emit('commit', $event.relatedTarget)"
        @enter="onEnter"
        @escape="onEscape"
      />
      <input
        v-else
        :id="id"
        class="input"
        :type="info.kind === 'password' ? 'password' : 'text'"
        :autocomplete="info.kind === 'password' ? 'new-password' : 'off'"
        spellcheck="false"
        :value="modelValue"
        :placeholder="placeholder"
        :readonly="info.kind === 'readonly'"
        :disabled="disabled"
        :aria-invalid="error !== ''"
        :aria-describedby="describedBy"
        @input="onInput"
        @blur="apply && emit('commit', $event.relatedTarget)"
        @keydown.enter="onEnter"
        @keydown.esc="onEscape"
      />
      <span v-if="info.unit" class="unit muted">{{ info.unit }}</span>
      <slot name="after"></slot>
      <InfoTip v-if="info.tip" :label="info.tipLabel ?? t('settings.about', { label: info.label })" :picture="info.picture">
        <span v-for="line in info.tip" :key="line" class="info-line">{{ line }}</span>
      </InfoTip>
    </div>
    <p v-if="error" :id="errorId" class="field-error" role="alert">{{ error }}</p>
    <p v-else-if="hint" class="field-hint muted">{{ hint }}</p>
  </div>
</template>
