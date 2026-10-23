<script setup lang="ts">
// One setting: its label, the input (a choice for a yes/no setting or a short list, read-only for one the daemon writes), the default as the placeholder, a unit after it, the daemon's complaint under it (or the result of a test, in the same place), and a slot after it for a button.
// A field whose meaning a word cannot say has an (i) after its label (InfoTip) with a few sentences and an example; one thing a word cannot say is the `title` of the field.
import { computed } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import type { Choice, FieldInfo } from "@/lib/settings";

const props = defineProps<{
  id: string;
  info: FieldInfo;
  modelValue: string;
  fallback: string;
  error: string;
  changed: boolean;
  result?: { ok: boolean; text: string } | null;
}>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();

const errorId = computed(() => `${props.id}-error`);
const describedBy = computed(() => (props.error ? errorId.value : undefined));
const placeholder = computed(() => props.info.empty ?? (props.fallback !== "" ? props.fallback : "(default)"));
// the unit, or the word for a value of 0 in its place ("never", "off")
const unit = computed(() => (props.info.zero !== undefined && props.modelValue.trim() === "0" ? props.info.zero : props.info.unit));

/** The options of a choice: the words for each value, and the value in force when it is none of them (a setting changed from the shell). */
const options = computed<Choice[]>(() => {
  const listed = (props.info.choices ?? []).map((c) => (typeof c === "string" ? { value: c, label: c } : c));
  return props.modelValue === "" || listed.some((c) => c.value === props.modelValue)
    ? listed
    : [...listed, { value: props.modelValue, label: props.modelValue }];
});

function onInput(event: Event): void {
  const target = event.target;
  if (target instanceof HTMLInputElement || target instanceof HTMLSelectElement) emit("update:modelValue", target.value);
}
</script>

<template>
  <div class="field" :class="{ changed, invalid: error !== '' }" :title="info.title">
    <div class="field-name">
      <label :for="id">{{ info.label }}</label>
      <InfoTip v-if="info.help" :label="info.label" :text="info.help" :example="info.example" />
    </div>
    <div class="field-control">
      <select v-if="info.kind === 'bool'" :id="id" class="input" :value="modelValue" :aria-describedby="describedBy" @change="onInput">
        <option value="true">yes</option>
        <option value="false">no</option>
      </select>
      <select v-else-if="info.kind === 'choice'" :id="id" class="input" :value="modelValue" :aria-describedby="describedBy" @change="onInput">
        <option v-for="choice in options" :key="choice.value" :value="choice.value">{{ choice.label }}</option>
      </select>
      <input
        v-else
        :id="id"
        class="input"
        type="text"
        autocomplete="off"
        spellcheck="false"
        :value="modelValue"
        :placeholder="placeholder"
        :readonly="info.kind === 'readonly'"
        :aria-invalid="error !== ''"
        :aria-describedby="describedBy"
        @input="onInput"
      />
      <span v-if="unit" class="unit muted">{{ unit }}</span>
      <slot name="after"></slot>
    </div>
    <p v-if="error" :id="errorId" class="field-error" role="alert">{{ error }}</p>
    <p v-else-if="result" class="field-error field-result" :class="{ ok: result.ok }" role="status">{{ result.text }}</p>
  </div>
</template>
