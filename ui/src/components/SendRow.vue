<script setup lang="ts">
// A line of the Beacon tab that says what was sent last and has the button that sends it now: the status line with Send status now (SendButton asks twice; the tab's useSendNow decides when it is on). On a phone the button is under the line, as wide as the line.
import SendButton from "@/components/SendButton.vue";

defineProps<{ label: string; text: string; hover?: string; button: string; armed: boolean; disabled: boolean; why?: string }>();
const emit = defineEmits<{ press: [] }>();
</script>

<template>
  <div class="sendrow">
    <dl class="card-fields">
      <dt>{{ label }}</dt>
      <dd :title="hover">{{ text }}</dd>
    </dl>
    <SendButton :label="button" :armed="armed" :disabled="disabled" :why="why" @press="emit('press')" />
  </div>
</template>
