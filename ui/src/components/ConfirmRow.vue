<script setup lang="ts">
// The question under a setting whose change could cut the device off ("This device will lose the page. Turn off?"), with Yes and Cancel. Cancel has the focus, and Esc cancels.
import { onMounted, ref } from "vue";

defineProps<{ message: string }>();
const emit = defineEmits<{ yes: []; cancel: [] }>();
const cancel = ref<HTMLButtonElement | null>(null);
onMounted(() => cancel.value?.focus());
</script>

<template>
  <div class="confirm-row" role="alertdialog" aria-label="Confirm" @keydown.esc.stop="emit('cancel')">
    <span>{{ message }}</span>
    <button class="btn danger" type="button" @click="emit('yes')">Yes</button>
    <button ref="cancel" class="btn" type="button" @click="emit('cancel')">Cancel</button>
  </div>
</template>
