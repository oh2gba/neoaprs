<script setup lang="ts">
// Ask around, the first box of the Nearby tab: one general query of APRS sent to the stations in radio range (the daemon's services/generalask.py), chosen in plain words (Who is around ?APRS?, iGates ?IGATE?, Weather stations ?WX?,
// each with its query in its hover title), and **Ask**. Under it the closed fold of the request's Path and RF only (RequestPath.vue; empty is the beacon's path, which the placeholder shows; remembered by this browser for this
// box apart from Local info's), then two quiet lines of a height that is always kept, so that nothing moves when their words change: what was asked, when and by what path, and that the answers arrive on the map and in Stations
// (before a query what Ask does, after a refusal the reason), and how many stations that had been quiet for ten minutes spoke in the two minutes after (their calls in the hover; they are likely answers, and the line does not say
// more). Ask is off, with the reason in its title, in RX only, while the path is wrong, and for the minute after a query of the same kind.
import { computed, ref, watch } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import RequestPath from "@/components/RequestPath.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { usePersisted } from "@/composables/usePersisted";
import { useRequestPath } from "@/composables/useRequestPath";
import { t } from "@/i18n";
import { errorReason } from "@/i18n/errortext";
import { GENERAL_KINDS, askLines, generalWait, queryOf } from "@/lib/askaround";

const { general, receiveOnly, send, lastError, now, fallbackPath } = useDaemonContext();
const kind = usePersisted("ask.kind", GENERAL_KINDS[0] ?? "aprs", GENERAL_KINDS);
const request = useRequestPath("ask");
const { path, rfOnly, problem } = request;
const refusal = ref(""); // (why the daemon refused the last Ask, until the next query)

const wait = computed(() => generalWait(general.value, kind.value, now.value));
const why = computed(() =>
  receiveOnly.value ? t("pill.rx_send") : problem.value !== "" ? problem.value : wait.value > 0 ? t("nearby.ask_wait", { seconds: wait.value }) : undefined,
);
const lines = computed(() => askLines(general.value, refusal.value, now.value));

watch(lastError, (toast) => {
  if (toast?.cmd === "general_query") refusal.value = errorReason(toast);
});
watch(
  () => general.value?.asked.at(-1)?.at,
  () => (refusal.value = ""),
);

function ask(): void {
  if (why.value !== undefined) return;
  refusal.value = "";
  send({ cmd: "general_query", kind: kind.value, path: request.sent.value, rf_only: rfOnly.value });
}
</script>

<template>
  <fieldset class="nearby-section nearby-ask">
    <legend class="nearby-head">
      {{ t("nearby.ask") }}
      <InfoTip :label="t('nearby.ask_tip_label')"
        ><span class="info-line">{{ t("nearby.ask_tip") }}</span></InfoTip
      >
    </legend>
    <div class="ask-row">
      <select v-model="kind" class="input ask-kind" :aria-label="t('nearby.ask_kind_label')" :title="queryOf(kind)">
        <option v-for="k in GENERAL_KINDS" :key="k" :value="k" :title="queryOf(k)">{{ t(`nearby.ask_kind.${k}`) }}</option>
      </select>
      <button type="button" class="btn" :disabled="why !== undefined" :title="why ?? t('nearby.ask_title', { query: queryOf(kind) })" @click="ask">
        {{ t("nearby.ask_button") }}
      </button>
    </div>
    <RequestPath v-model:path="path" v-model:rf-only="rfOnly" :usual="fallbackPath" :problem="problem" />
    <p class="ask-line" :class="lines.refused ? 'warn' : 'muted'" :title="lines.title || undefined">{{ lines.line }}</p>
    <p class="ask-line muted" :title="lines.countTitle || undefined">{{ lines.count }}</p>
  </fieldset>
</template>
