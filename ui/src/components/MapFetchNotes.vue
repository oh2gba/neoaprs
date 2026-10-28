<script setup lang="ts">
// What is under the button of the Detailed map row of the Map group of the Settings tab about the map's download: the progress of the job that runs (a bar and its step), what the last job failed with, and, quietly, "Map downloaded 23 Oct" when there is a detailed map.
// The button that starts and cancels the job is in the row (components/MapFetchButton.vue), the notes go in the row's notes slot (components/ActionRow.vue).
import { computed } from "vue";
import { downloadedLine, isRunning, progressText } from "@/lib/mapfetch";
import type { MapState } from "@/protocol/protocol";

const props = defineProps<{ map: MapState }>();
const running = computed(() => isRunning(props.map));
const progress = computed(() => progressText(props.map));
const done = computed(() => downloadedLine(props.map));
</script>

<template>
  <div v-if="running || (map.state === 'error' && map.problem) || done" class="mapfetch-notes">
    <div v-if="running" class="mapfetch-progress">
      <progress max="100" :value="map.percent ?? undefined" :aria-label="progress"></progress>
      <span class="muted" role="status">{{ progress }}</span>
    </div>
    <p v-if="map.state === 'error' && map.problem" class="field-error mapfetch-error" role="alert">{{ map.problem }}</p>
    <p v-if="done && !running" class="muted mapfetch-file">{{ done }}</p>
  </div>
</template>
