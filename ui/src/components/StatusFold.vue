<script setup lang="ts">
// THE status row of a group of the Settings tab, one look for every feature that has one (the Radio, Internet stations, the Digipeater, the Beacon and the Status report): under the group's tickbox, one line in view, the state as a word in the colour of the state (palette: connected
// ok, connecting and waiting warn, anything else muted) and the quiet detail beside it. The marks of the state are the top bar's; this is the plain words.
// An arrow in front opens what is behind it (the slot), and is there only when something is: a fold with nothing in it (a slot of lines that are all left out) is a plain row, with no arrow, nothing to click and the room of the arrow kept, so that the words stay under each other.
// The fold is closed unless `open` (which opens it when it turns true later and never closes it). `link` makes the line a link to the setting it explains (RX only), as the marks of the header lead to theirs (StatusLine.vue).
import { Comment, Fragment, Text, useSlots, type VNode } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import StatusLine from "@/components/StatusLine.vue";
import type { SettingLink } from "@/lib/settinglink";

withDefaults(defineProps<{ state: string; tone: string; line: string; hover?: string; open?: boolean; link?: SettingLink }>(), {
  hover: undefined,
  open: false,
  link: undefined,
});
const slots = useSlots();

/** Whether the nodes of a slot draw anything: a `v-if` that is false is a comment, a text of blanks is nothing. */
function drawn(nodes: readonly VNode[] | undefined): boolean {
  return (nodes ?? []).some((node) => {
    if (node.type === Comment) return false;
    if (node.type === Text) return typeof node.children !== "string" || node.children.trim() !== "";
    return node.type === Fragment ? drawn(Array.isArray(node.children) ? (node.children as VNode[]) : undefined) : true;
  });
}
</script>

<template>
  <DisclosureBox v-if="drawn(slots.default?.())" class="statusfold" :title="line" :open="open" summary-class="statushead">
    <template #summary><StatusLine :state="state" :tone="tone" :line="line" :hover="hover" :link="link" /></template>
    <slot></slot>
  </DisclosureBox>
  <div v-else class="statusfold statushead statusflat"><StatusLine :state="state" :tone="tone" :line="line" :hover="hover" :link="link" /></div>
</template>
