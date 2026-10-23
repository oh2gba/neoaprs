<script setup lang="ts">
// The delivery chain under a message of ours (lib/chain.ts): the chips of its latest attempt (the line above it already says which attempt that is). Nothing for a message with no attempt kept.
import { computed } from "vue";
import ChainChips from "@/components/ChainChips.vue";
import { chainOf } from "@/lib/chain";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ row: MessageRow; heardDirect?: ReadonlySet<string>; mail?: boolean }>(), {
  heardDirect: () => new Set<string>(),
  mail: false,
});

/** The chips of the latest attempt, or null when none is kept. */
const latest = computed(() => {
  const attempt = props.row.attempts_detail.at(-1);
  return attempt === undefined ? null : chainOf(props.row, attempt, true, props.heardDirect, props.mail);
});
</script>

<template>
  <div v-if="latest" class="chain">
    <ChainChips :chips="latest" class="chain-latest" />
  </div>
</template>
