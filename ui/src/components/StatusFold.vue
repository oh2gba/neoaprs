<script setup lang="ts">
// THE status row of a group of the Settings tab, one look for every feature that has one (the Radio, Internet stations): under the group's tickbox, one line in view, an arrow that opens what is behind it (the slot), the state as a word in the colour of the state (palette: connected
// ok, connecting and waiting warn, anything else muted), the quiet detail beside it, and at the end an action of the line if it has one (the slot `action`: Reconnect). The marks of the state are the top bar's; this is the plain words.
// The fold is closed unless `open` (which opens it when it turns true later and never closes it).
import DisclosureBox from "@/components/DisclosureBox.vue";

withDefaults(defineProps<{ state: string; tone: string; line: string; hover?: string; open?: boolean }>(), { hover: undefined, open: false });
</script>

<template>
  <DisclosureBox class="statusfold" :title="line" :open="open" summary-class="statushead">
    <template #summary>
      <span class="statetext" :class="tone">{{ state }}</span>
      <span class="tncstatus" role="status" :title="hover">{{ line }}</span>
      <slot name="action"></slot>
    </template>
    <slot></slot>
  </DisclosureBox>
</template>
