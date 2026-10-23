<script setup lang="ts">
// The buttons of the Map group of the Settings tab: Estimate (a dry run that says how big the detailed map will be), Download (the world map if it is not there, then the detailed map), Cancel while a job runs, the progress of the
// job and what it failed with, and the map files that are there. The daemon does the work for the area and the detail it has saved; unsaved changes of the form (`stale`) disable the buttons, unless the form saves them before
// it sends the command (`early`, the first-run guide), in which case the daemon having no position yet does not disable them either.
import { computed } from "vue";
import { currentEstimate, fileLines, formatBytes, isRunning, progressText } from "@/lib/mapfetch";
import type { Command, MapState } from "@/protocol/protocol";

const props = defineProps<{ map: MapState; stale: boolean; send: (command: Command) => boolean; early?: boolean }>();

const running = computed(() => isRunning(props.map));
const estimate = computed(() => currentEstimate(props.map));
const idle = computed(() => !running.value && !props.stale && (props.early || props.map.blocked === ""));
const why = computed(() =>
  props.stale ? (props.early ? undefined : "Save first") : running.value || props.early ? undefined : props.map.blocked || undefined,
);
const progress = computed(() => progressText(props.map));
const files = computed(() => fileLines(props.map));
</script>

<template>
  <div class="mapfetch">
    <div class="mapfetch-actions">
      <button class="btn" type="button" :disabled="!idle" :title="why" @click="send({ cmd: 'map_estimate' })">Estimate</button>
      <span v-if="estimate && !running" class="mapfetch-size" role="status">{{ formatBytes(estimate.bytes) }}</span>
      <button class="btn primary" type="button" :disabled="!idle" :title="why" @click="send({ cmd: 'map_fetch' })">Download</button>
      <button v-if="running" class="btn" type="button" @click="send({ cmd: 'map_cancel' })">Cancel</button>
    </div>
    <div v-if="running" class="mapfetch-progress">
      <progress max="100" :value="map.percent ?? undefined" :aria-label="progress"></progress>
      <span class="muted" role="status">{{ progress }}</span>
    </div>
    <p v-if="map.state === 'error' && map.problem" class="field-error mapfetch-error" role="alert">{{ map.problem }}</p>
    <p v-for="line in files" :key="line" class="muted mapfetch-file">{{ line }}</p>
  </div>
</template>
