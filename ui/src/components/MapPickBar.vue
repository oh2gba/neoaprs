<script setup lang="ts">
// A phone shows the map alone while a place is picked on it (the Beacon tab's and the Objects tab's Choose on map): this bar over the map says what to do and has Cancel, which ends the picking and brings the tab back.
import { t } from "@/i18n";

const emit = defineEmits<{ cancel: [] }>();
</script>

<template>
  <div class="pickbar" role="status">
    <span>{{ t("map.pick.tap") }}</span>
    <button type="button" class="btn small" @click="emit('cancel')">{{ t("map.pick.cancel") }}</button>
  </div>
</template>
