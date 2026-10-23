<script setup lang="ts">
// The toast after a setting was changed: "<name> changed" and an Undo button, which puts the old values back (one `set_config`). It stays for a few seconds (useSettings); the next change replaces it.
import { t } from "@/i18n";
import IconButton from "@/components/IconButton.vue";
import type { Undo } from "@/composables/useSettingsFeedback";

defineProps<{ undo: Undo | null }>();
const emit = defineEmits<{ undo: []; dismiss: [] }>();
</script>

<template>
  <div v-if="undo" :key="undo.n" class="toast undo" role="status">
    <span>{{ t("settings.undo.changed", { name: undo.label }) }}</span>
    <button class="linkbutton undo-button" type="button" @click="emit('undo')">{{ t("settings.undo.undo") }}</button>
    <IconButton kind="close" :label="t('common.dismiss')" :title="t('common.dismiss')" @click="emit('dismiss')" />
  </div>
</template>
