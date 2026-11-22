<script setup lang="ts">
// The small mark on a message of ours (lib/messages.ts `markOf`): clock while sending, check
// once acked, hollow check when no ack is expected, cross when failed or rejected, dash when
// cancelled. With `mail` a message whose attempts ran out is the hollow check, never a cross
// (lib/email.ts).
import { computed } from "vue";
import { mailMarkOf } from "@/lib/email";
import { markOf } from "@/lib/messages";
import type { MessageRow } from "@/protocol/protocol";

const props = defineProps<{ row: MessageRow; mail?: boolean }>();
const mark = computed(() => (props.mail ? mailMarkOf(props.row) : markOf(props.row)));
</script>

<template>
  <span
    v-if="mark"
    class="mark"
    :class="`mark-${mark.kind}`"
    role="img"
    :title="mark.title"
    :aria-label="mark.title"
    :data-mark="mark.kind"
  >
    <svg
      viewBox="0 0 12 12"
      width="12"
      height="12"
      fill="none"
      stroke="currentColor"
      stroke-width="1.6"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <template v-if="mark.kind === 'clock'">
        <circle cx="6" cy="6" r="4.8" />
        <path d="M6 3.4V6l1.9 1.2" />
      </template>
      <path v-else-if="mark.kind === 'check'" d="M2.2 6.4l2.6 2.6 5-5.6" />
      <template v-else-if="mark.kind === 'hollow'">
        <circle cx="6" cy="6" r="4.8" />
        <path d="M3.6 6.2l1.7 1.7 3.1-3.5" />
      </template>
      <path v-else-if="mark.kind === 'cross'" d="M3 3l6 6M9 3l-6 6" />
      <path v-else d="M2.8 6h6.4" />
    </svg>
  </span>
</template>
