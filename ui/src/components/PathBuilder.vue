<script setup lang="ts">
// The path builder of a path field: a small button beside the field that opens PathBuilderDialog.
// The dialog starts from the path in the field, or from `usual` when the field is empty.
// `use` writes the path built back to the field; `check` returns what is wrong with a path, or "".
// The dialog is teleported to the body so that no form or box around the field styles it, submits
// on Enter, or closes on a press that it takes for a press outside.
// `why` is the reason the button is off. `station` names the station whose Route this is.
// The digipeaters offered come from stations heard by a radio that may carry a path.
import { computed, inject, ref } from "vue";
import IconButton from "@/components/IconButton.vue";
import PathBuilderDialog from "@/components/PathBuilderDialog.vue";
import { DAEMON_KEY } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { t } from "@/i18n";
import { callsProblem, hopsOf } from "@/lib/pathbuilder";
import { homeFirst } from "@/lib/pathreach";
import type { StationRow } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{ value: string; usual: string; check?: (path: string) => string; station?: string; disabled?: boolean; why?: string }>(),
  {
    check: callsProblem,
    station: undefined,
    disabled: false,
    why: undefined,
  },
);
const emit = defineEmits<{ use: [path: string] }>();

const page = inject(DAEMON_KEY, null);
const radios = useRadios();
/** A station counts when a radio that may carry a path heard it (an unknown radio counts too). */
const counts = (row: StationRow): boolean => {
  const heard = Object.keys(row.heard ?? {});
  return heard.length === 0 || heard.some((id) => radios.byId(Number(id))?.carriesPath ?? true);
};
const stations = computed(() => new Map([...(page?.stations.value ?? new Map<string, StationRow>())].filter(([, row]) => counts(row))));
const now = computed(() => page?.now.value ?? Date.now());
const open = ref(false);
const trigger = ref<InstanceType<typeof IconButton> | null>(null);
const opener = computed(() => (trigger.value?.$el as HTMLElement | undefined) ?? null);
const start = computed(() => hopsOf(props.value.trim() !== "" ? props.value : props.usual));
/** Whether home digipeaters may take the first hop when the built path does not say. */
const home = computed(() => homeFirst(hopsOf(props.usual)) ?? true);

function close(): void {
  open.value = false;
}

function use(path: string): void {
  emit("use", path);
  close();
}
</script>

<template>
  <IconButton
    ref="trigger"
    kind="path"
    class="pathbuild-open"
    :label="t('pathbuilder.open')"
    :title="disabled ? why : undefined"
    :disabled="disabled"
    @click="open = true"
  />
  <Teleport v-if="open" to="body">
    <PathBuilderDialog
      :start="start"
      :home="home"
      :check="check"
      :station="station"
      :stations="stations"
      :now="now"
      :opener="opener"
      @use="use"
      @close="close"
    />
  </Teleport>
</template>
