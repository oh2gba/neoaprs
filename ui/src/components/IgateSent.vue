<script setup lang="ts">
// The lines that Send what I hear has put on APRS-IS, newest last, in the viewer's time with the tag
// of the radio that heard each: a list of a fixed height behind the Internet row's arrow, followed
// to its end unless scrolled up. The page asks the daemon for them (`igate_look`) only while the box
// is open and in view (useIgateLook). A line is other stations' text, shown as text only.
import { computed, nextTick, ref, watch } from "vue";
import TagMark from "@/components/TagMark.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { useInView } from "@/composables/useWhenShown";
import { t } from "@/i18n";
import { radioTag } from "@/lib/channels";
import { clockText } from "@/lib/format";

const props = defineProps<{ open: boolean }>();
const { igateSent, igateLook } = useDaemonContext();
const radios = useRadios();

const log = ref<HTMLElement | null>(null);
const inView = useInView(log);
igateLook.look(() => props.open && inView.value);
const FOLLOW_SLACK_PX = 24;
const rows = computed(() =>
  igateSent.value.map((one, n) => ({
    key: n,
    time: clockText(one.at),
    tag: one.radio === null ? null : radioTag(one.radio, radios.all.value),
    line: one.line,
  })),
);

watch(igateSent, async () => {
  const box = log.value;
  if (!box) return;
  const atEnd = box.scrollHeight - box.scrollTop - box.clientHeight <= FOLLOW_SLACK_PX;
  await nextTick();
  if (atEnd) box.scrollTop = box.scrollHeight;
});

/** The end of the lines is in view when the box is opened. */
watch(
  () => props.open,
  async (open) => {
    if (!open) return;
    await nextTick();
    if (log.value) log.value.scrollTop = log.value.scrollHeight;
  },
);
</script>

<template>
  <div ref="log" class="igatesent" role="log" :aria-label="t('settings.igate.sent_label')">
    <div v-for="row in rows" :key="row.key" class="igatesent-row">
      <span class="mono nowrap">{{ row.time }}</span>
      <span class="igatesent-tag"
        ><TagMark v-if="row.tag" :tone="row.tag.tone">{{ row.tag.label }}</TagMark></span
      >
      <span class="mono igatesent-line">{{ row.line }}</span>
    </div>
  </div>
</template>
