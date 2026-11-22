<script setup lang="ts">
// The status row of a Settings group, one look for every feature that has one: under the
// group's tickbox, one line with the state as a word in its colour (connected: ok; connecting
// and waiting: warn; else muted) and a quiet detail. The state marks are the top bar's.
// An arrow opens the slot content and exists only when the slot draws something; otherwise the
// row is plain, with the arrow's room kept so the words stay aligned. Closed unless `open`
// (which opens it when it turns true later, never closes it). `link` makes the line a link to
// the setting it explains; `parts` keeps the line's shape whatever it says (StatusLine.vue).
import { Comment, Fragment, Text, useSlots, type VNode } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import StatusLine from "@/components/StatusLine.vue";
import type { SettingLink } from "@/lib/settinglink";

withDefaults(
  defineProps<{ state: string; tone: string; line: string; hover?: string; open?: boolean; link?: SettingLink; parts?: readonly string[] | null }>(),
  {
    hover: undefined,
    parts: null,
    open: false,
    link: undefined,
  },
);
const slots = useSlots();

/** Whether the slot nodes draw anything: a false `v-if` leaves a comment, blank text is empty. */
function drawn(nodes: readonly VNode[] | undefined): boolean {
  return (nodes ?? []).some((node) => {
    if (node.type === Comment) return false;
    if (node.type === Text) return typeof node.children !== "string" || node.children.trim() !== "";
    return node.type === Fragment ? drawn(Array.isArray(node.children) ? (node.children as VNode[]) : undefined) : true;
  });
}
</script>

<template>
  <DisclosureBox
    v-if="drawn(slots.default?.())"
    class="statusfold"
    :title="line"
    :open="open"
    :summary-class="{ statushead: true, 'statushead-parts': parts !== null }"
  >
    <template #summary><StatusLine :state="state" :tone="tone" :line="line" :hover="hover" :link="link" :parts="parts" /></template>
    <slot></slot>
  </DisclosureBox>
  <div v-else class="statusfold statushead statusflat" :class="{ 'statushead-parts': parts !== null }">
    <StatusLine :state="state" :tone="tone" :line="line" :hover="hover" :link="link" :parts="parts" />
  </div>
</template>
