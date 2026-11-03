<script setup lang="ts">
// A box inside a group of the Settings tab, in the style of the group boxes: a fieldset with its legend (`title`; the slot `legend` is what stands after it, an (i)), so that it is plain which device a part of the Notifications group is for ("On the NeoAPRS computer", "In this browser"). Without a title it is only its content.
// With `foldId` the box folds as the groups do (the same fold, composables/useFold.ts, SettingsGroup.vue): the title is the button of an arrow in the legend, only what is under the legend closes, the state is kept in this browser (`settings.fold.ID`), the box is open at first,
// and it opens by itself when `show` turns true (a complaint of the daemon about one of its fields, a radio that is not connected) and when the page leads to a control inside it.
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
    <legend :title="hover">
      <button v-if="folds" type="button" class="groupfold" :aria-expanded="open" :aria-controls="bodyId" @click="open = !open">{{ title }}</button>
      <template v-else>{{ title }}{{ " " }}</template>
      <slot name="legend"></slot>
    </legend>
    <div v-if="folds" v-show="open" :id="bodyId" class="box-body"><slot></slot></div>
    <slot v-else></slot>
  </fieldset>
  <slot v-else></slot>
</template>
