<script setup lang="ts">
// The My station row that sends something now (Beacon now, Send status now): an ActionRow with a
// SendButton.
import ActionRow from "@/components/ActionRow.vue";
import SendButton from "@/components/SendButton.vue";

defineProps<{ id: string; label: string; tipLabel: string; tip: string; button: string; armed: boolean; disabled: boolean; why?: string }>();
const emit = defineEmits<{ press: [] }>();
</script>

<template>
  <ActionRow :id="id" :label="label" :tip-label="tipLabel">
    <SendButton :id="id" :label="button" :armed="armed" :disabled="disabled" :why="why" @press="emit('press')" />
    <template #tip
      ><span class="info-line">{{ tip }}</span></template
    >
  </ActionRow>
</template>
