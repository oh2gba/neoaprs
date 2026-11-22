<script setup lang="ts">
// The button that sends something now: a secondary button that asks twice (`armed` shows "Really
// send?", see TwoWords). The caller decides when it is `disabled` (with `why` on hover) and what a
// press does.
import TwoWords from "@/components/TwoWords.vue";
import { t } from "@/i18n";

defineProps<{ id?: string; label: string; armed: boolean; disabled: boolean; why?: string }>();
const emit = defineEmits<{ press: [] }>();
</script>

<template>
  <button :id="id" class="btn" :class="{ danger: armed }" type="button" :disabled="disabled" :title="why" @click="emit('press')">
    <TwoWords :second="armed"
      ><template #first>{{ label }}</template
      ><template #second>{{ t("beacon.really_send") }}</template></TwoWords
    >
  </button>
</template>
