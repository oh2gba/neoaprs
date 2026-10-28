<script setup lang="ts">
// The quiet line the page shows once after an update (composables/useWhatsNew.ts): "Updated to NeoAPRS 0.12.0 · What's new", in the place of the toasts and in the colours of a notice (ToastBar draws it when it has nothing
// else to say, so that an error is never under it). What's new opens the window of the update with the notes of every version since the one this browser saw before; that and the cross both end the line for this version.
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
