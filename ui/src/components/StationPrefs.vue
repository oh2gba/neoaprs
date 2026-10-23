<script setup lang="ts">
// What the operator has set for one station apart from what it says (the topic `station_prefs`, which the daemon keeps): the path its messages go by (a station can be messaged), how long it stays on
// the map after its last position, how many times a message to it is transmitted and whether it is RF only (the tickbox beside the path). Used on the station's card and in the header of a conversation; the fields say what they want, the page sends it. `suggested` is the path the daemon suggests for the station (null: none).
import StationAttempts from "@/components/StationAttempts.vue";
import StationPath from "@/components/StationPath.vue";
import StationRfOnly from "@/components/StationRfOnly.vue";
import StationTimeout from "@/components/StationTimeout.vue";
import type { Aging } from "@/lib/aging";
import type { Attempts } from "@/lib/attempts";

withDefaults(
  defineProps<{
    call: string;
    aging: Aging;
    attempts: Attempts;
    paths: ReadonlyMap<string, string>;
    fallbackPath: string;
    rfOnly?: ReadonlySet<string>;
    withPath?: boolean;
    withTimeout?: boolean;
    suggested?: string | null;
  }>(),
  {
    rfOnly: () => new Set<string>(),
    withPath: true,
    withTimeout: true,
    suggested: null,
  },
);
const emit = defineEmits<{
  path: [call: string, path: string];
  clearPath: [call: string];
  timeout: [call: string, minutes: number];
  clearTimeout: [call: string];
  setAttempts: [call: string, attempts: number];
  clearAttempts: [call: string];
  setRfOnly: [call: string, on: boolean];
}>();
</script>

<template>
  <div class="prefs">
    <StationPath
      v-if="withPath"
      :call="call"
      :paths="paths"
      :fallback="fallbackPath"
      :suggested="suggested"
      @set="(c, p) => emit('path', c, p)"
      @clear="emit('clearPath', $event)"
    >
      <StationRfOnly :call="call" :rf-only="rfOnly" @set="(c, on) => emit('setRfOnly', c, on)" />
    </StationPath>
    <StationTimeout v-if="withTimeout" :call="call" :aging="aging" @set="(c, m) => emit('timeout', c, m)" @clear="emit('clearTimeout', $event)" />
    <StationAttempts :call="call" :attempts="attempts" @set="(c, n) => emit('setAttempts', c, n)" @clear="emit('clearAttempts', $event)" />
  </div>
</template>
