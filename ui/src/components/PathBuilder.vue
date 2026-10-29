<script setup lang="ts">
// The path builder of a path field: the small button beside the field (the same everywhere a path is typed: the beacon's path in the My station tab, a station's Route in a conversation and in the Stations tab's panel, the Path of
// Ask around and of Local info, the path of an object) and the dialog it opens over the page (PathBuilderDialog). The dialog starts from the path in the field, or from the one in force when the field is empty (`usual`: the
// recommended path, the automatic one, the beacon's; empty is direct; whether home digipeaters may take the first hop starts as the usual path has it: WIDE1-1 first for a moving station, a wide hop for a fixed one), and Use gives the path built to the field (`use`: the calls separated by commas, DIRECT for none), which saves it the way the field saves what is typed;
// Cancel, Esc and a press beside the dialog leave the field as it is. `check` is the field's own rule (what is wrong with a path, "" when nothing is): Use is off while it finds something. `station` is the call of the station
// whose Route this is, for "As its packets come". The dialog is put at the end of the page's body (Teleport), so that it is not inside the field's form or its box: nothing of theirs styles it, Enter in it submits nothing,
// and the presses and the focus in it do not reach the box that the Route button opens, which would take them for a press outside and close, taking the dialog with it.
import { computed, inject, ref } from "vue";
import IconButton from "@/components/IconButton.vue";
import PathBuilderDialog from "@/components/PathBuilderDialog.vue";
import { DAEMON_KEY } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import { callsProblem, hopsOf } from "@/lib/pathbuilder";
import { homeFirst } from "@/lib/pathreach";
import type { StationRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ value: string; usual: string; check?: (path: string) => string; station?: string; disabled?: boolean }>(), {
  check: callsProblem,
  station: undefined,
  disabled: false,
});
const emit = defineEmits<{ use: [path: string] }>();

const page = inject(DAEMON_KEY, null);
const stations = computed(() => page?.stations.value ?? new Map<string, StationRow>());
const now = computed(() => page?.now.value ?? Date.now());
const open = ref(false);
const trigger = ref<InstanceType<typeof IconButton> | null>(null);
const opener = computed(() => (trigger.value?.$el as HTMLElement | undefined) ?? null);
const start = computed(() => hopsOf(props.value.trim() !== "" ? props.value : props.usual));
/** Whether home digipeaters may take the first hop when the path built says nothing of it: as the usual path has it (WIDE1-1 first for a moving station, a wide hop for a fixed one), else they may. */
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
  <IconButton ref="trigger" kind="path" class="pathbuild-open" :label="t('pathbuilder.open')" :disabled="disabled" @click="open = true" />
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
