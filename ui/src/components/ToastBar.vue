<script setup lang="ts">
// The last error the daemon (or the page) told, for a few seconds; a new one replaces it.
import { onBeforeUnmount, ref, watch } from "vue";
import IconButton from "@/components/IconButton.vue";
import type { Toast } from "@/composables/useDaemon";
import { t } from "@/i18n";
import { errorLine } from "@/i18n/errortext";

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
    <span>{{ errorLine(shown) }}</span>
    <IconButton kind="close" :label="t('common.dismiss')" :title="t('common.dismiss')" @click="shown = null" />
  </div>
</template>
