<script setup lang="ts">
// The button that sends something now (Beacon now, Send status now), shared by the beacon status and the status line of the Beacon tab: it asks twice (`armed`: it says "Really send?", in the danger colour); the tab's useSendNow decides when it is on
// (`disabled`, with `why` on hover) and what a press does.
import { t } from "@/i18n";

defineProps<{ label: string; armed: boolean; disabled: boolean; why?: string }>();
const emit = defineEmits<{ press: [] }>();
</script>

<template>
  <button class="btn primary" :class="{ danger: armed }" type="button" :disabled="disabled" :title="why" @click="emit('press')">
    {{ armed ? t("beacon.really_send") : label }}
  </button>
</template>
