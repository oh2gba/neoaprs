<script setup lang="ts">
// The row of Settings → Update check: the button Check now and, next to it, one line: the version of NeoAPRS (its hover title is what the daemon costs the machine: the CPU share, the memory, the uptime), and after it the outcome of the check in the colour of its meaning
// ("checking…", "up to date" in the ok colour, "0.10.1 available" with the button Update that opens the steps, "no answer" in the warn colour). The outcome goes after a few seconds; a newer version that is known stays.
import { computed } from "vue";
import ActionRow from "@/components/ActionRow.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import type { Outcome } from "@/composables/useUpdateCheck";
import { t } from "@/i18n";
import { processText } from "@/lib/format";

const props = defineProps<{ running: boolean; outcome: Outcome | null }>();
const emit = defineEmits<{ check: []; update: [] }>();
const { version, status } = useDaemonContext();

/** What the daemon costs the machine, as a sentence: "NeoAPRS uses 0.3 % of one processor core and 42 MB of memory, running for 3 h". */
const cost = computed(() => (status.value ? processText(status.value.cpu_percent, status.value.rss_mb, status.value.uptime_sec) : undefined));
const known = computed(() => status.value?.update?.version ?? null);
/** The word after the version: the check that is running, its outcome, or the newer version the daily check found. */
const word = computed<{ text: string; tone: string } | null>(() => {
  if (props.running) return { text: t("settings.update.checking"), tone: "tnc-stopped" };
  if (props.outcome) return { text: props.outcome.text, tone: props.outcome.tone };
  if (known.value) return { text: t("settings.update.available", { version: known.value }), tone: "update-available" };
  return null;
});
const offered = computed(() => known.value !== null && !props.running && (props.outcome === null || props.outcome.newer));
</script>

<template>
  <ActionRow id="set-update-now" :label="t('settings.update.label')" :tip-label="t('settings.update.tip_label')">
    <button id="set-update-now" class="btn" type="button" :disabled="running" @click="emit('check')">{{ t("settings.update.check") }}</button>
    <span class="updateline" role="status">
      <span v-if="version" class="updateversion" :title="cost">{{ t("settings.update.version", { version }) }}</span>
      <template v-if="word">
        <span aria-hidden="true">·</span> <span class="statetext" :class="word.tone">{{ word.text }}</span>
      </template>
      <button v-if="offered" type="button" class="btn" @click="emit('update')">{{ t("pill.update") }}</button>
    </span>
    <template #tip
      ><span class="info-line">{{ t("settings.update.tip") }}</span></template
    >
  </ActionRow>
</template>
