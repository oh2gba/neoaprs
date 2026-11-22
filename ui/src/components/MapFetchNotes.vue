<script setup lang="ts">
// The notes under the Detailed map button: the progress of the running job (a bar and its step),
// what the last job failed with and, quietly, "Map downloaded 23 Oct" when a detailed map
// exists. The button is MapFetchButton.vue; the notes fill the row's notes slot (ActionRow.vue).
import { computed } from "vue";
import { downloadedLine, isRunning, problemText, progressText } from "@/lib/mapfetch";
import type { MapState } from "@/protocol/protocol";

const props = defineProps<{ map: MapState }>();
const running = computed(() => isRunning(props.map));
const progress = computed(() => progressText(props.map));
const done = computed(() => downloadedLine(props.map));
const failed = computed(() => (props.map.state === "error" ? problemText(props.map) : ""));
</script>

<template>
  <div v-if="running || failed || done" class="mapfetch-notes">
    <div v-if="running" class="mapfetch-progress">
      <progress max="100" :value="map.percent ?? undefined" :aria-label="progress"></progress>
      <span class="muted" role="status">{{ progress }}</span>
    </div>
    <p v-if="failed" class="field-error mapfetch-error" role="alert">{{ failed }}</p>
    <p v-if="done && !running" class="muted mapfetch-file">{{ done }}</p>
  </div>
</template>
