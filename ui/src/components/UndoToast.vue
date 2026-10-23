<script setup lang="ts">
// The toast after a setting was changed: "<name> changed" and an Undo button, which puts the old values back (one `set_config`). It stays for a few seconds (useSettings); the next change replaces it.
import IconButton from "@/components/IconButton.vue";
import type { Undo } from "@/composables/useSettingsFeedback";

defineProps<{ undo: Undo | null }>();
const emit = defineEmits<{ undo: []; dismiss: [] }>();
</script>

<template>
  <div v-if="undo" :key="undo.n" class="toast undo" role="status">
    <span>{{ undo.label }} changed</span>
    <button class="linkbutton undo-button" type="button" @click="emit('undo')">Undo</button>
    <IconButton kind="close" label="Dismiss" title="Dismiss" @click="emit('dismiss')" />
  </div>
</template>
