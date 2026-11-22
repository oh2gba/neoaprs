<script setup lang="ts">
// A catalogue sentence with markup: the message names places like `{link}` or `{code}` and the
// caller fills each with a slot of that name. The sentence stays one message so that a language can
// reorder the pieces. Values that are text are `params`; a name with no value is a slot.
import { computed } from "vue";
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import type { Params } from "@/i18n/message";

const props = withDefaults(defineProps<{ id: MessageId; params?: Params }>(), { params: () => ({}) });

/** The text between the places, and the names of the places. */
const parts = computed(() =>
  t(props.id, props.params)
    .split(/\{(\w+)\}/)
    .map((part, i) => ({ part, slot: i % 2 === 1 })),
);
</script>

<template>
  <template v-for="(p, i) in parts" :key="i"
    ><slot v-if="p.slot" :name="p.part"></slot><template v-else>{{ p.part }}</template></template
  >
</template>
