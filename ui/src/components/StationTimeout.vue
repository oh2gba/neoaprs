<script setup lang="ts">
// How long after its last position a station stays on the map ("Hide from map after"): minutes, empty for the usual 3 hours (the placeholder says which), "never" (or 0) for never. It is saved when the
// field is changed and left, or Enter is pressed; an empty field takes the station's own timeout away, and so does the x.
import { computed, ref, useId, watch } from "vue";
import { NEVER, parseTimeoutText, timeoutText, type Aging } from "@/lib/aging";

const props = defineProps<{ call: string; aging: Aging }>();
const emit = defineEmits<{ set: [call: string, minutes: number]; clear: [call: string] }>();

const id = useId();
const own = computed(() => props.aging.timeouts.get(props.call) ?? null);
const text = computed(() => (own.value === null ? "" : own.value === 0 ? NEVER : String(own.value)));
const draft = ref(text.value);
const parsed = computed(() => parseTimeoutText(draft.value));
const minutes = computed(() => parsed.value !== null && parsed.value.minutes !== null && parsed.value.minutes > 0);

watch([() => props.call, text], () => (draft.value = text.value));

function save(): void {
  const result = parsed.value;
  if (result === null) return;
  if (result.minutes === null) {
    draft.value = "";
    if (own.value !== null) emit("clear", props.call);
  } else if (result.minutes !== own.value) {
    draft.value = result.minutes === 0 ? NEVER : String(result.minutes);
    emit("set", props.call, result.minutes);
  } else {
    draft.value = text.value;
  }
}
</script>

<template>
  <div class="pathbox timeoutbox">
    <label :for="id" class="path-label">Hide from map after</label>
    <input
      :id="id"
      v-model="draft"
      class="input mono timeout-input"
      :class="{ invalid: parsed === null }"
      type="text"
      inputmode="numeric"
      :placeholder="`${timeoutText(aging.defaultMin)} (usual)`"
      :title="parsed === null ? 'Whole minutes, or never' : 'Minutes, or never; empty for the usual time'"
      autocomplete="off"
      spellcheck="false"
      @change="save"
    />
    <span v-if="minutes" class="muted">min</span>
    <button
      v-if="own !== null"
      type="button"
      class="iconbtn use-default"
      aria-label="Use the default timeout"
      title="Use the default timeout"
      @click="emit('clear', call)"
    >
      ×
    </button>
  </div>
</template>
