<script setup lang="ts">
// The quiet line shown once after an update (composables/useWhatsNew.ts): "Updated to NeoAPRS
// 0.12.0 · What's new", in the toast place and in notice colours. ToastBar draws it only when
// it has nothing else to say, so an error is never under it. What's new opens the update window
// with the notes of every version since the one this browser last saw; that and the cross both
// end the line for this version.
import IconButton from "@/components/IconButton.vue";
import { t } from "@/i18n";

defineProps<{ version: string }>();
const emit = defineEmits<{ open: []; dismiss: [] }>();
</script>

<template>
  <span>{{ t("help.update.updated", { version }) }}</span>
  <button type="button" class="linkbutton whatsnew-open" @click="emit('open')">{{ t("help.update.news") }}</button>
  <IconButton kind="close" :label="t('common.dismiss')" :title="t('common.dismiss')" @click="emit('dismiss')" />
</template>
