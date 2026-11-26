<script setup lang="ts">
// One setting: label, input (checkbox, choice, call with SSID, or read-only), default as
// placeholder, unit, the daemon's complaint and a slot for a button. Events: `update:modelValue`
// while typing and on a choice, `commit` when a typed field ends (Enter or blur), `cancel` for Esc
// in a changed field. A `disabled` field is greyed with its value. A field with `count` shows a
// counter and takes no more than the limit (lib/textlimit.ts typedInto). `info.tip` adds an (i).
import { computed } from "vue";
import CallInput from "@/components/CallInput.vue";
import InfoTip from "@/components/InfoTip.vue";
import LeftCounter from "@/components/LeftCounter.vue";
import { t } from "@/i18n";
import { leftTitle } from "@/lib/compose";
import { confirms } from "@/lib/ime";
import type { Choice } from "@/lib/settingchoices";
import type { FieldInfo } from "@/lib/settings";
import { leftOf, type TextLimit, typedInto } from "@/lib/textlimit";

const props = defineProps<{
  id: string;
  info: FieldInfo;
  modelValue: string;
  fallback: string;
  error: string;
  changed: boolean;
  /**
   * the field applies as it is changed (the settings form): Enter and blur say `commit`, Esc says
   * `cancel`; else it belongs to a form with a button, where Enter submits
   */
  apply?: boolean;
  /**
   * greyed out: control and label are dimmed and cannot be changed, the value is kept (the (i)
   * still opens)
   */
  disabled?: boolean;
  /** the limit of a typed field: its counter, and typing stops there */
  count?: TextLimit | undefined;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: string];
  choose: [value: string];
  commit: [next: EventTarget | null];
  cancel: [];
}>();

const errorId = computed(() => `${props.id}-error`);
const describedBy = computed(() => (props.error ? errorId.value : undefined));
/** What is left of the limit; negative when the value is already longer. */
const left = computed(() => (props.count === undefined ? 0 : leftOf(props.modelValue, props.count)));
const placeholder = computed(
  () => props.info.empty ?? (props.fallback !== "" ? props.fallback : t("settings.default_placeholder")),
);

/**
 * The options of a choice: the words for each value, plus the value in force if it is none of them.
 */
const options = computed<Choice[]>(() => {
  const listed = (props.info.choices ?? []).map((c) => (typeof c === "string" ? { value: c, label: c } : c));
  return props.modelValue === "" || listed.some((c) => c.value === props.modelValue)
    ? listed
    : [...listed, { value: props.modelValue, label: props.info.other?.(props.modelValue) ?? props.modelValue }];
});

/**
 * The options as the list draws them: grouped options under a heading (`optgroup`), the rest alone.
 */
const sections = computed<{ group: string | undefined; choices: Choice[] }[]>(() =>
  options.value.reduce<{ group: string | undefined; choices: Choice[] }[]>((runs, choice) => {
    const last = runs.at(-1);
    if (last !== undefined && last.group === choice.group) last.choices.push(choice);
    else runs.push({ group: choice.group, choices: [choice] });
    return runs;
  }, []),
);

function onInput(event: Event): void {
  const target = event.target;
  const choice =
    target instanceof HTMLSelectElement || (target instanceof HTMLInputElement && target.type === "checkbox");
  const value =
    props.count !== undefined && target instanceof HTMLInputElement && target.type !== "checkbox"
      ? typedInto(event, props.modelValue, props.count)
      : target instanceof HTMLInputElement && target.type === "checkbox"
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
  if (!props.apply || !confirms(event)) return;
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
        <template v-for="section in sections" :key="section.choices[0]?.value">
          <optgroup v-if="section.group !== undefined" :label="section.group">
            <option
              v-for="choice in section.choices"
              :key="choice.value"
              :value="choice.value"
              :title="choice.title"
              :disabled="choice.disabled"
            >
              {{ choice.label }}
            </option>
          </optgroup>
          <template v-else>
            <option
              v-for="choice in section.choices"
              :key="choice.value"
              :value="choice.value"
              :title="choice.title"
              :disabled="choice.disabled"
            >
              {{ choice.label }}
            </option>
          </template>
        </template>
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
        :maxlength="info.maxLength"
        :readonly="info.kind === 'readonly'"
        :disabled="disabled"
        :aria-invalid="error !== ''"
        :aria-describedby="describedBy"
        @input="onInput"
        @compositionend="onInput"
        @blur="apply && emit('commit', $event.relatedTarget)"
        @keydown.enter="onEnter"
        @keydown.esc="onEscape"
      />
      <LeftCounter v-if="count" :left="left" :max="count.max" :title="leftTitle(left, count.kind, count.max)" />
      <span v-if="info.unit" class="unit muted">{{ info.unit }}</span>
      <slot name="after"></slot>
      <InfoTip
        v-if="info.tip"
        :label="info.tipLabel ?? t('settings.about', { label: info.label })"
        :picture="info.picture"
      >
        <span v-for="line in info.tip" :key="line" class="info-line">{{ line }}</span>
      </InfoTip>
    </div>
    <p v-if="error" :id="errorId" class="field-error" role="alert">{{ error }}</p>
  </div>
</template>
