<script setup lang="ts">
// A phone shows the map alone while a place is picked on it (My station, Objects): this bar says
// what to do and has Cancel, which ends the picking and brings the tab back.
import { t } from "@/i18n";

const emit = defineEmits<{ cancel: [] }>();
</script>

<template>
  <div class="pickbar" role="status">
    <span>{{ t("map.pick.tap") }}</span>
    <button type="button" class="btn" @click="emit('cancel')">{{ t("map.pick.cancel") }}</button>
  </div>
</template>
