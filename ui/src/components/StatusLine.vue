<script setup lang="ts">
// The words of a status row (StatusFold): the state in the colour of its tone and the quiet line beside it, which is a link to a setting when it explains one (`link`: the id of the control in the Settings tab and the hover title; a click opens the tab and flashes the group, lib/attention.ts).
// Two elements and no root of its own: they are the content of the row's heading, whether the row folds or not.
import { useOpenSetting } from "@/composables/useOpenSetting";
import type { SettingLink } from "@/lib/settinglink";

defineProps<{ state: string; tone: string; line: string; hover?: string; link?: SettingLink }>();
const goTo = useOpenSetting();
</script>

<template>
  <span class="statetext" :class="tone">{{ state }}</span>
  <span class="tncstatus" role="status" :title="hover">
    <button v-if="link && goTo" type="button" class="linkbutton" :title="link.title" @click.stop.prevent="goTo('settings', link.control)">{{ line }}</button>
    <template v-else>{{ line }}</template>
  </span>
</template>
