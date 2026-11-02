<script setup lang="ts">
// The small picture of an encrypted message (a padlock) and of a key announcement (a key), in the line of the marks of a message (MessageMark: 12 by 12, the colour of the text, round ends). `title` says what it means.
withDefaults(defineProps<{ kind: "lock" | "key"; title: string; size?: number }>(), { size: 12 });
</script>

<template>
  <span class="mark" :class="`mark-${kind}`" role="img" :title="title" :aria-label="title" :data-mark="kind">
    <svg
      :viewBox="`0 0 12 12`"
      :width="size"
      :height="size"
      fill="none"
      stroke="currentColor"
      stroke-width="1.4"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <template v-if="kind === 'lock'">
        <rect x="2.2" y="5.4" width="7.6" height="5.4" rx="1.2" />
        <path d="M3.8 5.4V3.9a2.2 2.2 0 0 1 4.4 0v1.5" />
      </template>
      <template v-else>
        <circle cx="4" cy="6" r="2.4" />
        <path d="M6.4 6h4.2M9 6v1.8M10.6 6v1.3" />
      </template>
    </svg>
  </span>
</template>
