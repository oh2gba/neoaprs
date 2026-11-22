<script setup lang="ts">
// The Settings → Update check row: the Check now button and one line with the NeoAPRS version
// (its title shows what the daemon costs: CPU share, memory, uptime) followed by the outcome in
// its meaning's colour ("checking…", "up to date", "1.2.3 available" with an Update button,
// "no answer"). The outcome clears after a few seconds; a known newer version stays. The
// What's new link follows the version (composables/useWhatsNew.ts) so nothing moves when the
// words change.
import { computed } from "vue";
import ActionRow from "@/components/ActionRow.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import type { Outcome } from "@/composables/useUpdateCheck";
import { t } from "@/i18n";
import { processText } from "@/lib/format";

const props = defineProps<{ running: boolean; outcome: Outcome | null }>();
const emit = defineEmits<{ check: []; update: []; notes: [] }>();
const { version, status } = useDaemonContext();

/** What the daemon costs the machine, as a sentence ("NeoAPRS uses 0.3 % of one processor core
 * and 42 MB of memory, running for 3 h"). */
const cost = computed(() =>
  status.value ? processText(status.value.cpu_percent, status.value.rss_mb, status.value.uptime_sec) : undefined,
);
const known = computed(() => status.value?.update?.version ?? null);
/** The word after the version: running check, outcome, or the newer version found daily. */
const word = computed<{ text: string; tone: string } | null>(() => {
  if (props.running) return { text: t("settings.update.checking"), tone: "tnc-stopped" };
  if (props.outcome) return { text: props.outcome.text, tone: props.outcome.tone };
  if (known.value) return { text: t("settings.update.available", { version: known.value }), tone: "update-available" };
  return null;
});
const offered = computed(
  () => known.value !== null && !props.running && (props.outcome === null || props.outcome.newer),
);
</script>

<template>
  <ActionRow id="set-update-now" :label="t('settings.update.label')" :tip-label="t('settings.update.tip_label')">
    <button id="set-update-now" class="btn" type="button" :disabled="running" @click="emit('check')">
      {{ t("settings.update.check") }}
    </button>
    <span class="updateline" role="status">
      <template v-if="version">
        <span class="updateversion" :title="cost">{{ t("settings.update.version", { version }) }}</span>
        <button type="button" class="linkbutton updatenotes" @click="emit('notes')">{{ t("help.update.news") }}</button>
      </template>
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
