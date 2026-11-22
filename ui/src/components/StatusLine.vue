<script setup lang="ts">
// The words of a status row (StatusFold): the state in its tone colour and a quiet line beside
// it. `link` (a control id in the Settings tab, also the title) turns the line into a link
// that opens the tab and flashes the group (lib/attention.ts). `parts` are lines that change
// while nothing else does; each stays on one line, ellipsised, so the row keeps its height
// (settings.css `.statushead-parts`). The separator dot is not drawn, but keeps the text whole.
// Renders two elements without a root: the content of the row's heading.
import { useOpenSetting } from "@/composables/useOpenSetting";
import type { SettingLink } from "@/lib/settinglink";

defineProps<{
  state: string;
  tone: string;
  line: string;
  hover?: string;
  link?: SettingLink;
  parts?: readonly string[] | null;
}>();
const goTo = useOpenSetting();
</script>

<template>
  <span class="statetext" :class="tone">{{ state }}</span>
  <span class="tncstatus" :class="{ statusparts: parts }" role="status" :title="hover">
    <button
      v-if="link && goTo"
      type="button"
      class="linkbutton"
      :title="link.title"
      @click.stop.prevent="goTo('settings', link.control)"
    >
      {{ line }}
    </button>
    <template v-else-if="parts"
      ><template v-for="(part, index) in parts" :key="index"
        ><span v-if="index > 0" class="statuspart-dot"> · </span
        ><span class="statuspart" :class="{ 'statuspart-more': index > 0 }">{{ part }}</span></template
      ></template
    >
    <template v-else>{{ line }}</template>
  </span>
</template>
