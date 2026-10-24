<script setup lang="ts">
// How messages to one station are sent (the topic `station_prefs`, which the daemon keeps): the path they go by and whether it is RF only (the tickbox beside the path).
// In the header of a conversation; the fields say what they want, the page sends it. `heard` is the path that has lately been heard to reach the station (null: none), which the automatic choice of the first attempts goes by.
import StationPath from "@/components/StationPath.vue";
import StationRfOnly from "@/components/StationRfOnly.vue";

withDefaults(
  defineProps<{
    call: string;
    paths: ReadonlyMap<string, string>;
    fallbackPath: string;
    rfOnly?: ReadonlySet<string>;
    heard?: string | null;
  }>(),
  {
    rfOnly: () => new Set<string>(),
    heard: null,
  },
);
const emit = defineEmits<{
  path: [call: string, path: string];
  clearPath: [call: string];
  setRfOnly: [call: string, on: boolean];
}>();
</script>

<template>
  <div class="prefs">
    <StationPath :call="call" :paths="paths" :fallback="fallbackPath" :heard="heard" @set="(c, p) => emit('path', c, p)" @clear="emit('clearPath', $event)">
      <StationRfOnly :call="call" :rf-only="rfOnly" @set="(c, on) => emit('setRfOnly', c, on)" />
    </StationPath>
  </div>
</template>
