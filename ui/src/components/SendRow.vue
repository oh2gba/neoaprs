<script setup lang="ts">
// A line of the Beacon tab that says what was sent last and has the button that sends it now: "Last beacon: 2 min ago" (the full time on hover) with Beacon now, or the status line with Send status now. The button asks twice (`armed`: it says
// "Really send?"); the tab's useSendNow decides when it is on. On a phone the button is under the line, as wide as the line.
import { t } from "@/i18n";

defineProps<{ label: string; text: string; hover?: string; button: string; armed: boolean; disabled: boolean; why?: string }>();
const emit = defineEmits<{ press: [] }>();
</script>

<template>
  <div class="sendrow">
    <dl class="card-fields">
      <dt>{{ label }}</dt>
      <dd :title="hover">{{ text }}</dd>
    </dl>
    <button class="btn primary" :class="{ danger: armed }" type="button" :disabled="disabled" :title="why" @click="emit('press')">
      {{ armed ? t("beacon.really_send") : button }}
    </button>
  </div>
</template>
