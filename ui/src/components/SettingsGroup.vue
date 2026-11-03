<script setup lang="ts">
// A group of the Settings tab: a fieldset with its legend (the group's name), which folds by the arrow in front of the name (a button with `aria-expanded` and `aria-controls`, the arrow of the page's other folds, StatusFold). Only what is under the legend closes: the legend row keeps its
// place and size. What the person left (open or folded) is kept in this browser for each group (composables/useFold.ts, `settings.fold.ID`); a group that was never folded is open, so a new group is. What is folded stays on the page (hidden), so that the page can still find a control in it.
// A group opens by itself when it has something the person must see: `show` turns true (a complaint of the daemon about one of its fields, a question it asks), and when the page leads to a control inside it (lib/attention.ts sends REVEAL_EVENT to the control before it scrolls and focuses).
// Without `fold` (the My station tab's groups) it is the plain group box. The boxes inside a group that fold (SettingsBox) use the same fold.
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
