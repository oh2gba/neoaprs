<script setup lang="ts">
// A group of the Settings tab: a fieldset whose legend folds by its arrow (button with
// `aria-expanded` and `aria-controls`). Only what is under the legend closes. The state is kept per
// group in this browser (useFold, `settings.fold.ID`); a new group is open. Folded content stays in
// the page so that a control in it can still be found. A group opens by itself when `show` turns
// true or when the page leads to a control inside it (lib/attention.ts sends REVEAL_EVENT). Without
// `fold` it is a plain box.
import { computed, ref } from "vue";
import { useFold } from "@/composables/useFold";

const props = withDefaults(defineProps<{ id: string; title: string; fold?: boolean; show?: boolean }>(), { fold: true, show: false });
const root = ref<HTMLElement | null>(null);
const { open } = useFold(props.id, () => props.show, root);
const bodyId = computed(() => `settings-group-${props.id}`);
</script>

<template>
  <fieldset ref="root" :class="{ folded: fold && !open }">
    <legend>
      <button v-if="fold" type="button" class="groupfold" :aria-expanded="open" :aria-controls="bodyId" @click="open = !open">{{ title }}</button>
      <template v-else>{{ title }}</template>
    </legend>
    <div v-show="!fold || open" :id="fold ? bodyId : undefined" class="group-body"><slot></slot></div>
  </fieldset>
</template>
