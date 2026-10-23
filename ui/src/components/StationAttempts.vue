<script setup lang="ts">
// How many times a message to the station is transmitted before it has failed: 1 to 10, empty for the default of the setting messages/attempts (the placeholder says which). With 1 or 2 a message that gets no
// ack is "unconfirmed", not failed. It is saved when the field is changed and left, or Enter is pressed; an empty field takes the station's own count away, and so does the x.
import { computed, ref, useId, watch } from "vue";
import { parseAttemptsText, type Attempts } from "@/lib/attempts";
import { MESSAGE_ATTEMPTS_MAX } from "@/protocol/lists";

const props = defineProps<{ call: string; attempts: Attempts }>();
const emit = defineEmits<{ set: [call: string, attempts: number]; clear: [call: string] }>();

const id = useId();
const own = computed(() => props.attempts.own.get(props.call) ?? null);
const text = computed(() => (own.value === null ? "" : String(own.value)));
const draft = ref(text.value);
const parsed = computed(() => parseAttemptsText(draft.value));

watch([() => props.call, text], () => (draft.value = text.value));

function save(): void {
  const result = parsed.value;
  if (result === null) return;
  if (result.count === null) {
    draft.value = "";
    if (own.value !== null) emit("clear", props.call);
  } else if (result.count !== own.value) {
    draft.value = String(result.count);
    emit("set", props.call, result.count);
  } else {
    draft.value = text.value;
  }
}
</script>

<template>
  <div class="pathbox attemptsbox">
    <label :for="id" class="path-label">Attempts</label>
    <input
      :id="id"
      v-model="draft"
      class="input mono attempts-input"
      :class="{ invalid: parsed === null }"
      type="text"
      inputmode="numeric"
      :placeholder="`(default: ${attempts.defaultCount})`"
      :title="parsed === null ? `Whole number, 1 to ${MESSAGE_ATTEMPTS_MAX}` : undefined"
      autocomplete="off"
      spellcheck="false"
      @change="save"
    />
    <button
      v-if="own !== null"
      type="button"
      class="iconbtn use-default"
      aria-label="Use the default attempts"
      title="Use the default attempts"
      @click="emit('clear', call)"
    >
      ×
    </button>
  </div>
</template>
