<script setup lang="ts">
// The terminal of a radio, closed until wanted: the latest lines of what the TNC saw and did,
// newest last, in the viewer's time, following the end unless scrolled up. It sits under the
// radio status in Settings and under the Radio step fields of the setup guide; `toggle` reports
// opening or closing (the guide puts the shown radio in force when it opens).
import { computed, nextTick, ref, watch } from "vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import { t } from "@/i18n";
import { lineText } from "@/lib/tncstatus";
import type { RadioRow } from "@/protocol/protocol";

const props = defineProps<{ tnc: Pick<RadioRow, "lines"> | null }>();
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
