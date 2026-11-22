<script setup lang="ts">
// The delivery chain under a message of ours (lib/chain.ts): the chips of its latest attempt,
// the first naming the radio where radios are named. Nothing for a message with no attempt kept.
import { computed } from "vue";
import ChainChips from "@/components/ChainChips.vue";
import { useRadios } from "@/composables/useRadios";
import { chainOf } from "@/lib/chain";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ row: MessageRow; heardDirect?: ReadonlySet<string>; mail?: boolean }>(), {
  heardDirect: () => new Set<string>(),
  mail: false,
});

const radios = useRadios();
/** The name on the "you" chip: the attempt's radio where radios are named; null otherwise. */
const radioName = (id: number | null): string | null => (id !== null && radios.named(id) ? (radios.byId(id)?.name ?? null) : null);

/** The chips of the latest attempt, or null when none is kept. */
const latest = computed(() => {
  const attempt = props.row.attempts_detail.at(-1);
  return attempt === undefined ? null : chainOf(props.row, attempt, true, props.heardDirect, props.mail, radioName(attempt.radio_id));
});
</script>

<template>
  <div v-if="latest" class="chain">
    <ChainChips :chips="latest" class="chain-latest" />
  </div>
</template>
