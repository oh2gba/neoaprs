<script setup lang="ts">
// The small drawings of the path builder's picture, in the style of the page's icon buttons: "you",
// "wide", "any", "none" and "air". Only a picture; the meaning is in the hover title of what holds
// it.
defineProps<{ kind: "you" | "wide" | "any" | "none" | "air" }>();
</script>

<template>
  <svg
    class="pathglyph"
    :width="kind === 'any' ? 30 : 16"
    height="16"
    :viewBox="kind === 'any' ? '0 0 30 16' : '0 0 16 16'"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-if="kind === 'you'">
      <circle cx="8" cy="5" r="2.6" />
      <path d="M3 14a5 5 0 0 1 10 0" />
    </template>
    <template v-else-if="kind === 'wide' || kind === 'any'">
      <path v-if="kind === 'any'" d="M1 8l6-5 6 5M2.5 7v6.5h9V7M5.5 13.5V10h3v3.5" />
      <g :transform="kind === 'any' ? 'translate(14 0)' : undefined">
        <circle cx="8" cy="5" r="1" />
        <path d="M5.4 2.6a3.4 3.4 0 0 0 0 4.8M10.6 2.6a3.4 3.4 0 0 1 0 4.8M8 7l-3 7M8 7l3 7M6 11.5h4" />
      </g>
    </template>
    <template v-else-if="kind === 'none'">
      <circle cx="8" cy="8" r="5.5" />
      <path d="M4.2 11.8l7.6-7.6" />
    </template>
    <template v-else>
      <circle cx="8" cy="8" r="1" />
      <path
        d="M5.4 5.4a3.7 3.7 0 0 0 0 5.2M10.6 5.4a3.7 3.7 0 0 1 0 5.2M3.2 3.2a6.8 6.8 0 0 0 0 9.6M12.8 3.2a6.8 6.8 0 0 1 0 9.6"
      />
    </template>
  </svg>
</template>
