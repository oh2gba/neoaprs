<script setup lang="ts">
// How messages to one station are sent (the topic `station_prefs`, which the daemon keeps): the path they go by, whether it is RF only (the tickbox beside the path) and how many times a message is transmitted.
// In the header of a conversation; the fields say what they want, the page sends it. `suggested` is the path the daemon suggests for the station (null: none).
import StationAttempts from "@/components/StationAttempts.vue";
import StationPath from "@/components/StationPath.vue";
import StationRfOnly from "@/components/StationRfOnly.vue";
import type { Attempts } from "@/lib/attempts";

withDefaults(
  defineProps<{
    call: string;
    attempts: Attempts;
    paths: ReadonlyMap<string, string>;
    fallbackPath: string;
    rfOnly?: ReadonlySet<string>;
    suggested?: string | null;
  }>(),
  {
    rfOnly: () => new Set<string>(),
    suggested: null,
  },
);
const emit = defineEmits<{
  path: [call: string, path: string];
  clearPath: [call: string];
  setAttempts: [call: string, attempts: number];
  clearAttempts: [call: string];
  setRfOnly: [call: string, on: boolean];
}>();
</script>

<template>
  <div class="prefs">
    <StationPath
      :call="call"
      :paths="paths"
      :fallback="fallbackPath"
      :suggested="suggested"
      @set="(c, p) => emit('path', c, p)"
      @clear="emit('clearPath', $event)"
    >
      <StationRfOnly :call="call" :rf-only="rfOnly" @set="(c, on) => emit('setRfOnly', c, on)" />
    </StationPath>
    <StationAttempts :call="call" :attempts="attempts" @set="(c, n) => emit('setAttempts', c, n)" @clear="emit('clearAttempts', $event)" />
  </div>
</template>
