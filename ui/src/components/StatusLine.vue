<script setup lang="ts">
// The words of a status row (StatusFold): the state in the colour of its tone and the quiet line beside it, which is a link to a setting when it explains one (`link`: the id of the control in the Settings tab and the hover title; a click opens the tab and flashes the group, lib/attention.ts).
// A line that changes while nothing else does (a connected radio's: what its modem does, when a packet last came) comes in its `parts`, each on a line of its own that is never wrapped and is cut with an ellipsis where
// the row is too narrow (the whole line is the hover title the caller gives), so that the row is as high whatever the parts say and nothing under it moves: the first part beside the state, the next under the state
// for the whole width of the row (settings.css `.statushead-parts`). The dot between two parts is not drawn; it is there so that the element's text is the whole line. Two elements and no root of its own: they are
// the content of the row's heading, whether the row folds or not.
import { useOpenSetting } from "@/composables/useOpenSetting";
import type { SettingLink } from "@/lib/settinglink";

defineProps<{ state: string; tone: string; line: string; hover?: string; link?: SettingLink; parts?: readonly string[] | null }>();
const goTo = useOpenSetting();
</script>

<template>
  <span class="statetext" :class="tone">{{ state }}</span>
  <span class="tncstatus" :class="{ statusparts: parts }" role="status" :title="hover">
    <button v-if="link && goTo" type="button" class="linkbutton" :title="link.title" @click.stop.prevent="goTo('settings', link.control)">{{ line }}</button>
    <template v-else-if="parts"
      ><template v-for="(part, index) in parts" :key="index"
        ><span v-if="index > 0" class="statuspart-dot"> · </span><span class="statuspart" :class="{ 'statuspart-more': index > 0 }">{{ part }}</span></template
      ></template
    >
    <template v-else>{{ line }}</template>
  </span>
</template>
