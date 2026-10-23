<script setup lang="ts">
// The path a message to a station, and the ack of one from it, goes by way of: the digipeaters, separated by commas. A station has the path of the setting beacon/path until it is given one of
// its own ("(default)" says which it is); an empty path of its own is direct (the placeholder). The path is saved when the field is changed and left, or Enter is pressed (the browser's change event),
// and the x takes it away again. What is put in the slot (the RF only tickbox) sits beside it. The chip "suggested: ..." fills the field with the path the daemon worked out from how the station's packets reach us (the best route turned round) and saves it; it
// is not there when there is no suggestion or the station has it already.
import { computed, ref, useId, watch } from "vue";
import { parsePath } from "@/lib/calls";
import { effectivePath } from "@/lib/messages";
import { pathWords } from "@/lib/routes";

const props = withDefaults(defineProps<{ call: string; paths: ReadonlyMap<string, string>; fallback: string; suggested?: string | null }>(), {
  suggested: null,
});
const emit = defineEmits<{ set: [call: string, path: string]; clear: [call: string] }>();

const id = useId();
const effective = computed(() => effectivePath(props.paths, props.fallback, props.call));
const draft = ref(effective.value.text);
const calls = computed(() => parsePath(draft.value));
const applied = computed(() => props.suggested === null || (effective.value.own && effective.value.text === props.suggested));

watch([() => props.call, effective], () => (draft.value = effective.value.text));

function save(): void {
  const list = calls.value;
  if (list === null) return;
  const text = list.join(",");
  draft.value = text;
  if (text !== effective.value.text) emit("set", props.call, text);
}

function useSuggested(): void {
  if (props.suggested === null) return;
  draft.value = props.suggested;
  emit("set", props.call, props.suggested);
}
</script>

<template>
  <div class="pathbox">
    <label :for="id" class="path-label">Path</label>
    <input
      :id="id"
      v-model="draft"
      class="input mono grow"
      :class="{ invalid: calls === null }"
      type="text"
      placeholder="direct"
      :title="calls === null ? 'Calls separated by commas, at most 8' : undefined"
      autocomplete="off"
      spellcheck="false"
      @change="save"
    />
    <span v-if="!effective.own" class="muted">(default)</span>
    <button v-else type="button" class="iconbtn use-default" aria-label="Use the default path" title="Use the default path" @click="emit('clear', call)">
      ×
    </button>
    <button v-if="suggested !== null && !applied" type="button" class="chip use-suggested" @click="useSuggested">suggested: {{ pathWords(suggested) }}</button>
    <slot />
  </div>
</template>
