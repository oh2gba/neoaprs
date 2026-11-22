<script setup lang="ts">
// A serial port as one control: "find automatically" (the empty port; "not set" for the GPS), the
// ports the system lists, and "Other..." for a typed path or socket address. When automatic and the
// daemon knows the radio, the last port is shown beside it (`serial/last_port`). A listed port is a
// choice (`choose`); a typed path applies on Enter or blur (`commit`); Esc (`cancel`) restores it.
import { computed, ref, watch } from "vue";
import SettingsField from "@/components/SettingsField.vue";
import { t } from "@/i18n";
import { PORT_OTHER, portOptions, type HolderOf } from "@/lib/portchoice";
import type { FieldInfo } from "@/lib/settings";
import type { PortsMessage } from "@/protocol/protocol";

const props = defineProps<{
  id: string;
  info: FieldInfo;
  modelValue: string;
  /** serial/last_port as the daemon has it */
  found: string;
  /** the empty port means "not set", not "find automatically" (the GPS receiver) */
  unset?: boolean;
  ports: PortsMessage | null;
  /**
   * who holds each port, for this box (a port held by another radio or the GPS is greyed with its
   * name)
   */
  holder?: HolderOf;
  error: string;
  changed: boolean;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: string];
  choose: [value: string];
  commit: [next: EventTarget | null];
  cancel: [];
  refresh: [];
}>();

const typing = ref(false);
const options = computed(() => portOptions(props.ports, props.modelValue, props.found, props.unset, props.holder));
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

// a path the daemon refused stays in the field
watch(
  () => props.error,
  (now) => {
    if (
      now !== "" &&
      props.changed &&
      props.modelValue !== "" &&
      !props.ports?.ports.some((p) => p.device === props.modelValue)
    )
      typing.value = true;
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
        :aria-label="t('settings.port.path_label')"
        @input="type"
        @blur="leave"
        @keydown.enter.prevent="emit('commit', null)"
        @keydown.esc="escape"
      />
      <span v-else-if="modelValue === '' && found !== ''" class="muted port-found">{{
        t("settings.port.found", { port: found })
      }}</span>
      <button type="button" class="btn" @click="emit('refresh')">{{ t("settings.port.refresh") }}</button>
    </template>
  </SettingsField>
</template>
