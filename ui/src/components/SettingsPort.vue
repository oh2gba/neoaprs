<script setup lang="ts">
// The TNC's port as one control: a choice of "find automatically" (the empty port), the ports the system lists and "Other..." for a path or a socket address typed. When the port is automatic and the daemon has found the radio before, that
// port is told beside the control (it is the daemon's own memory, `serial/last_port`, and not a field). Refresh asks the system for its ports again. A port picked from the list is a choice (`choose`, at once); a path typed applies on Enter or when
// the field is left (`commit`), and Esc (`cancel`) puts the port in force back.
import { computed, ref, watch } from "vue";
import SettingsField from "@/components/SettingsField.vue";
import { PORT_OTHER, portOptions } from "@/lib/portchoice";
import type { FieldInfo } from "@/lib/settings";
import type { PortsMessage } from "@/protocol/protocol";

const props = defineProps<{
  id: string;
  info: FieldInfo;
  modelValue: string;
  /** serial/last_port as the daemon has it */
  found: string;
  ports: PortsMessage | null;
  error: string;
  changed: boolean;
}>();
const emit = defineEmits<{ "update:modelValue": [value: string]; choose: [value: string]; commit: [next: EventTarget | null]; cancel: []; refresh: [] }>();

const typing = ref(false);
const options = computed(() => portOptions(props.ports, props.modelValue, props.found));
const field = computed<FieldInfo>(() => ({ ...props.info, kind: "choice", choices: options.value }));

function pick(value: string): void {
  typing.value = value === PORT_OTHER;
  if (!typing.value) emit("choose", value);
}

function type(event: Event): void {
  if (event.target instanceof HTMLInputElement) emit("update:modelValue", event.target.value);
}

function leave(event: FocusEvent): void {
  emit("commit", event.relatedTarget);
  typing.value = false;
}

function escape(event: KeyboardEvent): void {
  event.stopPropagation();
  emit("cancel");
  typing.value = false;
}

// a path the daemon refused stays in the field it was typed in
watch(
  () => props.error,
  (now) => {
    if (now !== "" && props.changed && props.modelValue !== "" && !props.ports?.ports.some((p) => p.device === props.modelValue)) typing.value = true;
  },
);
</script>

<template>
  <SettingsField
    :id="id"
    :info="field"
    :model-value="typing ? PORT_OTHER : modelValue"
    fallback=""
    :error="error"
    :changed="changed"
    @update:model-value="pick"
  >
    <template #after>
      <input
        v-if="typing"
        :id="`${id}-typed`"
        class="input"
        type="text"
        autocomplete="off"
        spellcheck="false"
        :value="modelValue"
        :placeholder="info.empty"
        aria-label="Port path"
        @input="type"
        @blur="leave"
        @keydown.enter.prevent="emit('commit', null)"
        @keydown.esc="escape"
      />
      <span v-else-if="modelValue === '' && found !== ''" class="muted port-found">found: {{ found }}</span>
      <button type="button" class="btn" @click="emit('refresh')">Refresh</button>
    </template>
  </SettingsField>
</template>
