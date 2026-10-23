<script setup lang="ts">
// The delivery chain under a message of ours (lib/chain.ts): the chips of its latest attempt, and when it was sent more than once a line "3 attempts" that opens the chains of all of them, the newest first. Nothing for a message with no attempt kept.
import { computed } from "vue";
import ChainChips from "@/components/ChainChips.vue";
import { attemptsText, chainOf } from "@/lib/chain";
import { clockText } from "@/lib/format";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ row: MessageRow; heardDirect?: ReadonlySet<string>; mail?: boolean }>(), {
  heardDirect: () => new Set<string>(),
  mail: false,
});

/** Every attempt with its chips, the newest first. */
const attempts = computed(() => {
  const all = props.row.attempts_detail;
  return all
    .map((attempt, index) => ({
      number: index + 1,
      sentAt: attempt.sent_at,
      chips: chainOf(props.row, attempt, index === all.length - 1, props.heardDirect, props.mail),
    }))
    .reverse();
});
</script>

<template>
  <div v-if="attempts.length > 0" class="chain">
    <ChainChips :chips="attempts[0]?.chips ?? []" class="chain-latest" />
    <details v-if="attempts.length > 1" class="chain-earlier">
      <summary>{{ attemptsText(attempts.length) }}</summary>
      <div v-for="a in attempts" :key="a.number" class="chain-attempt">
        <span class="chain-sent muted" :title="`attempt ${a.number}`">{{ a.number }} · {{ clockText(a.sentAt) }}</span>
        <ChainChips :chips="a.chips" />
      </div>
    </details>
  </div>
</template>
