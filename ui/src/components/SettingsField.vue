<script setup lang="ts">
// One setting: its label, the input (a checkbox for a yes/no setting, a choice for a short list, the call with its SSID dropdown, read-only for one the daemon writes), the default as the placeholder, a unit after it, the daemon's complaint under it, and a slot after it for a button. What it says of itself: `update:modelValue` with the text as it is typed (and for a choice), `choose`
// when a choice is made (a list, a switch), `commit` when a typed field is finished with Enter or left (with the element focus went to), `cancel` for Esc in a field that holds a change or a complaint.
// A `disabled` field is shown greyed with its value, as the My station tab shows what belongs to a beacon that is Off. A typed field with a limit (`count`: the beacon's comment, the status) has the counter of every text with a limit right of it (LeftCounter, as the
// box to write a message in has), and takes no more than the limit (lib/textlimit.ts typedInto, as every field with a counter): what goes beyond it is cut there, and a value that is already longer can only be made shorter. A field whose meaning a non-developer may not know has a small (i) after it (`info.tip`); nothing else explains it, and the one thing a word cannot say is the `title` of the field.
import { computed } from "vue";
import CallInput from "@/components/CallInput.vue";
import InfoTip from "@/components/InfoTip.vue";
import LeftCounter from "@/components/LeftCounter.vue";
import { t } from "@/i18n";
import { leftTitle } from "@/lib/compose";
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
  /** the field applies as it is changed (the settings form): Enter and leaving it say `commit`, Esc says `cancel`; else it is a field of a form with a button (the setup guide), where Enter submits */
  apply?: boolean;
  /** greyed out: the control and its label are dimmed and cannot be changed, the value is kept (the (i) still opens) */
  disabled?: boolean;
  /** the limit of a typed field: its counter, and typing stops there */
  count?: TextLimit | undefined;
}>();
const emit = defineEmits<{ "update:modelValue": [value: string]; choose: [value: string]; commit: [next: EventTarget | null]; cancel: [] }>();

const errorId = computed(() => `${props.id}-error`);
const describedBy = computed(() => (props.error ? errorId.value : undefined));
/** What is left of the limit; negative when the value is already longer ("3 over"). */
const left = computed(() => (props.count === undefined ? 0 : leftOf(props.modelValue, props.count)));
const placeholder = computed(() => props.info.empty ?? (props.fallback !== "" ? props.fallback : t("settings.default_placeholder")));

/** The options of a choice: the words for each value, and the value in force when it is none of them (a setting changed from the shell). */
const options = computed<Choice[]>(() => {
  const listed = (props.info.choices ?? []).map((c) => (typeof c === "string" ? { value: c, label: c } : c));
  return props.modelValue === "" || listed.some((c) => c.value === props.modelValue)
    ? listed
    : [...listed, { value: props.modelValue, label: props.info.other?.(props.modelValue) ?? props.modelValue }];
});

/** The options as the list draws them: each run of options of one group under its heading (an `optgroup`), those of no group by themselves. */
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
  const choice = target instanceof HTMLSelectElement || (target instanceof HTMLInputElement && target.type === "checkbox");
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
        <template v-for="section in sections" :key="section.choices[0]?.value">
          <optgroup v-if="section.group !== undefined" :label="section.group">
            <option v-for="choice in section.choices" :key="choice.value" :value="choice.value" :title="choice.title" :disabled="choice.disabled">
              {{ choice.label }}
            </option>
          </optgroup>
          <template v-else>
            <option v-for="choice in section.choices" :key="choice.value" :value="choice.value" :title="choice.title" :disabled="choice.disabled">
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
      <InfoTip v-if="info.tip" :label="info.tipLabel ?? t('settings.about', { label: info.label })" :picture="info.picture">
        <span v-for="line in info.tip" :key="line" class="info-line">{{ line }}</span>
      </InfoTip>
    </div>
    <p v-if="error" :id="errorId" class="field-error" role="alert">{{ error }}</p>
  </div>
</template>
