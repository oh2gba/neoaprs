<script setup lang="ts">
// The call as the Beacon tab and the setup guide ask for it: the call without its SSID in a text field, and the SSID in a dropdown beside it (the recommendations of aprs.org, so that nobody has to look up the number). The value is the call as
// the settings keep it (`OH2GBA-9`), put together here and taken apart again. The field takes letters and digits in capitals; a dash with a number after it, typed or pasted (`OH2GBA-9`), moves the number into the dropdown (and out of the
// field when the field is left, or at once when it was pasted); nothing else is let in. Choosing in the dropdown says `choose` (a call is there to be sent), but not while the field holds no call.
import { computed, ref, watch } from "vue";
import { t } from "@/i18n";
import { callInput, joinCall, splitCall } from "@/lib/calls";
import { ssidChoices } from "@/lib/settingchoices";

const props = defineProps<{ id: string; modelValue: string; placeholder: string; disabled?: boolean; invalid: boolean; describedby?: string }>();
const emit = defineEmits<{
  "update:modelValue": [value: string];
  choose: [value: string];
  blur: [event: FocusEvent];
  enter: [event: KeyboardEvent];
  escape: [event: KeyboardEvent];
}>();

const first = splitCall(props.modelValue);
/** What the field shows: the call, and for a moment the dash and number being typed. */
const text = ref(first.base);
const ssid = ref(first.ssid);
const choices = computed(() => ssidChoices());
const joined = (): string => joinCall(callInput(text.value).base, ssid.value);

// a value that came from outside (Esc, an undo, a change from another page) is shown; the value this field has just said is not shown again, so that a dash being typed stays
watch(
  () => props.modelValue,
  (value) => {
    if (value === joined()) return;
    const now = splitCall(value);
    text.value = now.base;
    if (now.base !== "") ssid.value = now.ssid;
  },
);

function typed(event: Event): void {
  const field = event.target;
  if (!(field instanceof HTMLInputElement)) return;
  const pasted = /^insertFrom(Paste|Drop)/.test((event as Partial<InputEvent>).inputType ?? "");
  const input = callInput(field.value);
  text.value = pasted ? input.base : input.text;
  field.value = text.value;
  if (input.ssid !== null) ssid.value = input.ssid;
  emit("update:modelValue", joinCall(input.base, ssid.value));
}

/** The field is finished with: the number that was being typed stays only in the dropdown. */
function settle(field: EventTarget | null): void {
  text.value = callInput(text.value).base;
  if (field instanceof HTMLInputElement) field.value = text.value;
}

function onBlur(event: FocusEvent): void {
  settle(event.target);
  emit("blur", event);
}

function onEnter(event: KeyboardEvent): void {
  settle(event.target);
  emit("enter", event);
}

function pick(event: Event): void {
  if (!(event.target instanceof HTMLSelectElement)) return;
  ssid.value = event.target.value;
  const call = joined();
  emit("update:modelValue", call);
  if (callInput(text.value).base !== "") emit("choose", call);
}
</script>

<template>
  <div class="callrow">
    <input
      :id="id"
      class="input callbase"
      type="text"
      autocomplete="off"
      spellcheck="false"
      autocapitalize="characters"
      :value="text"
      :placeholder="placeholder"
      :disabled="disabled"
      :aria-invalid="invalid"
      :aria-describedby="describedby"
      @input="typed"
      @blur="onBlur"
      @keydown.enter="onEnter"
      @keydown.esc="emit('escape', $event)"
    />
    <select :id="`${id}-ssid`" class="input ssid" :value="ssid" :disabled="disabled" :aria-label="t('settings.ssid.label')" @change="pick">
      <option v-for="choice in choices" :key="choice.value" :value="choice.value">{{ choice.label }}</option>
    </select>
  </div>
</template>
