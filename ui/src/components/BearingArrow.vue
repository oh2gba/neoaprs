<script setup lang="ts">
// A direction as a small arrow, north up, turned by the angle: the bearing to a station in the Stations table, and the direction an antenna favours on a station's card. No direction (an omni antenna) is a small circle.
// It says nothing in words; the caller gives the words (the compass point and the degrees) as the hover title and to a screen reader (`label`).
withDefaults(defineProps<{ deg: number | null; label?: string; size?: number }>(), { label: undefined, size: 14 });
</script>

<template>
  <svg
    class="arrow"
    :width="size"
    :height="size"
    viewBox="0 0 14 14"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    :style="deg === null ? undefined : { transform: `rotate(${deg}deg)` }"
    :role="label === undefined ? undefined : 'img'"
    :aria-label="label"
    :aria-hidden="label === undefined ? 'true' : undefined"
  >
    <circle v-if="deg === null" cx="7" cy="7" r="3" />
    <path v-else d="M7 12.5V2M3 6l4-4 4 4" />
  </svg>
</template>
