<script setup lang="ts">
// "Alert me when…" for one station (from the menu of a row of the Stations table): a small box where the menu was, with the three things the daemon can watch (StationAlertChoices: it comes on the air, it comes within so many km
// of us, 10 to start with, it is heard direct), and Save and Cancel. It shows the alert the station has, takes the focus on its first tickbox and keeps
// inside the window. Esc and Cancel close it with the focus back on `trigger` (the row or its "..." button), Save does too after it has sent the whole alert (all off takes it away), and a press outside it closes it. The daemon keeps
// the alert and fires it, with no page open too (lib/stationalert.ts).
import { computed, nextTick, onMounted, ref } from "vue";
import StationAlertChoices from "@/components/StationAlertChoices.vue";
import { useAlertDraft } from "@/composables/useAlertDraft";
import { usePopup } from "@/composables/usePopup";
import { t } from "@/i18n";
import type { AlertWhen } from "@/protocol/protocol";

const MARGIN = 8;

const props = defineProps<{ call: string; alert: AlertWhen | null; x: number; y: number; trigger: HTMLElement | null; placed: boolean }>();
const emit = defineEmits<{ save: [call: string, alert: AlertWhen]; close: [] }>();

const { onAir, near, km, direct, kmOk, alert } = useAlertDraft(() => props.alert);

const root = ref<HTMLElement | null>(null);
const open = ref(false);
const at = ref({ left: props.x, top: props.y });

function close(): void {
  open.value = false;
  emit("close");
}
/** Closed with the focus back where the menu was opened from. */
function finish(): void {
  close();
  props.trigger?.focus();
}
const popup = usePopup({ open, root, trigger: computed(() => props.trigger), close, focusAway: false, stopEscape: true });

onMounted(async () => {
  open.value = true;
  await nextTick();
  const box = root.value?.getBoundingClientRect();
  if (box) {
    at.value = {
      left: Math.max(MARGIN, Math.min(props.x, window.innerWidth - box.width - MARGIN)),
      top: Math.max(MARGIN, Math.min(props.y, window.innerHeight - box.height - MARGIN)),
    };
  }
  root.value?.querySelector<HTMLInputElement>("input[data-alert='on_air']")?.focus();
});

function save(): void {
  const value = alert();
  if (value === null) return;
  emit("save", props.call, value);
  finish();
}
</script>

<template>
  <div
    ref="root"
    class="alertbox"
    role="dialog"
    :aria-label="t('station.alert.label', { call })"
    :style="{ left: `${at.left}px`, top: `${at.top}px` }"
    @keydown="popup.onEscape"
    @contextmenu.prevent
  >
    <form @submit.prevent="save">
      <StationAlertChoices v-model:on-air="onAir" v-model:near="near" v-model:km="km" v-model:direct="direct" :call="call" :placed="placed" :km-ok="kmOk">
        <span class="alertbox-buttons">
          <button type="submit" class="btn primary" :disabled="near && !kmOk">{{ t("station.alert.save") }}</button>
          <button type="button" class="btn" @click="finish">{{ t("station.alert.cancel") }}</button>
        </span>
      </StationAlertChoices>
    </form>
  </div>
</template>
