<script setup lang="ts">
// The last error the daemon (or the page) told, for a few seconds; a new one replaces it.
import { onBeforeUnmount, ref, watch } from "vue";
import type { Toast } from "@/composables/useDaemon";

const props = defineProps<{ toast: Toast | null; seconds?: number }>();

const shown = ref<Toast | null>(null);
let timer: ReturnType<typeof setTimeout> | undefined;

watch(
  () => props.toast,
  (toast) => {
    clearTimeout(timer);
    shown.value = toast;
    if (toast) timer = setTimeout(() => (shown.value = null), (props.seconds ?? 8) * 1000);
  },
);
onBeforeUnmount(() => clearTimeout(timer));
</script>

<template>
  <div v-if="shown" class="toast" role="alert">
    <span>{{ shown.text }}</span>
    <button class="iconbtn" type="button" aria-label="Dismiss" @click="shown = null">x</button>
  </div>
</template>
