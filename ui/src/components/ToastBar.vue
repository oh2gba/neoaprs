<script setup lang="ts">
// The last error from the daemon or the page, shown for a few seconds; a new one replaces it.
// The RX only error links to its tickbox (lib/settinglink.ts). A notice
// (composables/useNotice.ts) takes the same place in the Undo toast colours.
// The slot holds a line that stays until dismissed (WhatsNewLine.vue); it is drawn in notice
// colours while there is nothing else to say and returns after that is gone, so the two never
// overlap.
import { onBeforeUnmount, ref, watch } from "vue";
import IconButton from "@/components/IconButton.vue";
import type { Toast } from "@/composables/useDaemon";
import type { Notice } from "@/composables/useNotice";
import { t } from "@/i18n";
import { errorLine } from "@/i18n/errortext";
import { useOpenSetting } from "@/composables/useOpenSetting";
import { useRadios } from "@/composables/useRadios";
import { rxOnlyLink } from "@/lib/settinglink";

const props = defineProps<{ toast: Toast | null; notice?: Notice | null; seconds?: number }>();

const shown = ref<Toast | Notice | null>(null);
const goTo = useOpenSetting();
// A refusal that names a radio is shown as the page names it.
const radios = useRadios();
let timer: ReturnType<typeof setTimeout> | undefined;

function show(next: Toast | Notice | null): void {
  clearTimeout(timer);
  shown.value = next;
  if (next) timer = setTimeout(() => (shown.value = null), (props.seconds ?? 8) * 1000);
}
// Clearing an error never removes a notice shown since.
watch(
  () => props.toast,
  (toast) => {
    if (toast !== null || (shown.value !== null && "cmd" in shown.value)) show(toast);
  },
);
watch(
  () => props.notice,
  (notice) => show(notice ?? null),
);
onBeforeUnmount(() => clearTimeout(timer));
</script>

<template>
  <div v-if="shown && 'cmd' in shown" class="toast" role="alert">
    <button
      v-if="goTo && shown.code === 'transmit.off'"
      type="button"
      class="linkbutton"
      :title="rxOnlyLink().title"
      @click="goTo('settings', rxOnlyLink().control)"
    >
      {{ errorLine(shown, radios) }}
    </button>
    <span v-else>{{ errorLine(shown, radios) }}</span>
    <IconButton kind="close" :label="t('common.dismiss')" :title="t('common.dismiss')" @click="shown = null" />
  </div>
  <div v-else-if="shown" :key="shown.n" class="toast notice" role="status">
    <span>{{ shown.text }}</span>
    <IconButton kind="close" :label="t('common.dismiss')" :title="t('common.dismiss')" @click="shown = null" />
  </div>
  <div v-else-if="$slots.default" class="toast notice" role="status">
    <slot />
  </div>
</template>
