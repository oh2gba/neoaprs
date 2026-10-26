<script setup lang="ts">
// The terminal of the radio, closed until it is wanted: the latest lines of what the TNC saw and did, newest last, in the viewer's time, following the end unless it was scrolled up. It is under the radio status of the Settings tab
// and under the fields of the Radio step of the setup guide; `toggle` says whether it was opened or closed (the guide puts the radio it shows in force when it opens).
import { computed, nextTick, ref, watch } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import { t } from "@/i18n";
import { lineText } from "@/lib/tncstatus";
import type { TncState } from "@/protocol/protocol";

const props = defineProps<{ tnc: TncState | null }>();
const emit = defineEmits<{ toggle: [open: boolean] }>();

const log = ref<HTMLElement | null>(null);
const FOLLOW_SLACK_PX = 24;
const lines = computed(() => (props.tnc?.lines ?? []).map(lineText));

watch(
  () => props.tnc?.lines,
  async () => {
    const box = log.value;
    if (!box) return;
    const atEnd = box.scrollHeight - box.scrollTop - box.clientHeight <= FOLLOW_SLACK_PX;
    await nextTick();
    if (atEnd) box.scrollTop = box.scrollHeight;
  },
);

/** The end of the lines is in view when the terminal is opened. */
async function toggled(event: Event): Promise<void> {
  const open = event.target instanceof HTMLDetailsElement && event.target.open;
  emit("toggle", open);
  if (!open) return;
  await nextTick();
  if (log.value) log.value.scrollTop = log.value.scrollHeight;
}
</script>

<template>
  <DisclosureBox :title="t('settings.tnc.terminal')" @toggle="toggled">
    <pre ref="log" class="tnclines" :aria-label="t('settings.tnc.terminal_label')">{{ lines.join("\n") }}</pre>
  </DisclosureBox>
</template>
