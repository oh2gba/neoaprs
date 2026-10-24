<script setup lang="ts">
// The last error the daemon (or the page) told, for a few seconds; a new one replaces it. A notice (composables/useNotice.ts: "Asked OH2XYZ for its status") takes the same place, in the colours of the Undo toast, and is replaced by whatever comes next.
import { onBeforeUnmount, ref, watch } from "vue";
import IconButton from "@/components/IconButton.vue";
import type { Toast } from "@/composables/useDaemon";
import type { Notice } from "@/composables/useNotice";
import { t } from "@/i18n";
import { errorLine } from "@/i18n/errortext";

const props = defineProps<{ toast: Toast | null; notice?: Notice | null; seconds?: number }>();

const shown = ref<Toast | Notice | null>(null);
let timer: ReturnType<typeof setTimeout> | undefined;

function show(next: Toast | Notice | null): void {
  clearTimeout(timer);
  shown.value = next;
  if (next) timer = setTimeout(() => (shown.value = null), (props.seconds ?? 8) * 1000);
}
watch(
  () => props.toast,
  (toast) => show(toast),
);
watch(
  () => props.notice,
  (notice) => show(notice ?? null),
);
onBeforeUnmount(() => clearTimeout(timer));
</script>

<template>
  <div v-if="shown && 'cmd' in shown" class="toast" role="alert">
    <span>{{ errorLine(shown) }}</span>
    <IconButton kind="close" :label="t('common.dismiss')" :title="t('common.dismiss')" @click="shown = null" />
  </div>
  <div v-else-if="shown" :key="shown.n" class="toast notice" role="status">
    <span>{{ shown.text }}</span>
    <IconButton kind="close" :label="t('common.dismiss')" :title="t('common.dismiss')" @click="shown = null" />
  </div>
</template>
