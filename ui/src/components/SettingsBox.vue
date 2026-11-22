<script setup lang="ts">
// A box inside a group of the Settings tab: a fieldset with a legend (`title`; the slot `legend`
// follows it). With `foldId` the box folds like a group and the state is kept in this browser; it
// opens by itself when `show` turns true or when the page leads to a control inside it.
import { computed, ref } from "vue";
import { useFold } from "@/composables/useFold";

const props = defineProps<{ title?: string; hover?: string; foldId?: string; show?: boolean }>();
const root = ref<HTMLElement | null>(null);
const { open } = useFold(props.foldId ?? "", () => props.show === true, root);
const folds = computed(() => props.foldId !== undefined);
const bodyId = computed(() => `settings-box-${props.foldId ?? ""}`);
</script>

<template>
  <fieldset v-if="title" ref="root" class="subbox" :class="{ folded: folds && !open }">
    <legend :title="hover || undefined">
      <button
        v-if="folds"
        type="button"
        class="groupfold"
        :aria-expanded="open"
        :aria-controls="bodyId"
        @click="open = !open"
      >
        {{ title }}
      </button>
      <template v-else>{{ title }}{{ " " }}</template>
      <slot name="legend"></slot>
    </legend>
    <div v-if="folds" v-show="open" :id="bodyId" class="box-body"><slot></slot></div>
    <slot v-else></slot>
  </fieldset>
  <slot v-else></slot>
</template>
