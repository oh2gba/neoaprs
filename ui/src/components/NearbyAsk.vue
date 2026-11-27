<script setup lang="ts">
// Ask around, the first box of the Nearby tab: one general APRS query to the stations in radio
// range (the daemon's services/generalask.py), chosen in plain words, and **Ask**. While several
// sending radios are on, Send on follows (SendOn.vue, `radio/<id>/ask`), then the closed fold of
// the request's Path (RequestPath.vue, shared with Local info). Two quiet lines of
// fixed height follow: what was asked, when and by what path, and how many stations that had
// been quiet for ten minutes spoke in the two minutes after. The query goes once on each ticked
// connected radio. Ask is off, with the reason in its title, in RX only, while no radio of it is
// connected, while the path is wrong and for the minute after a query of the same kind.
import { computed, ref, watch } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import RequestPath from "@/components/RequestPath.vue";
import SendOn from "@/components/SendOn.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useCommandInFlight } from "@/composables/useInFlight";
import { usePersisted } from "@/composables/usePersisted";
import { useRadios } from "@/composables/useRadios";
import { useRequestPath } from "@/composables/useRequestPath";
import { useSendOn } from "@/composables/useSendOn";
import { t } from "@/i18n";
import { errorReason } from "@/i18n/errortext";
import { GENERAL_KINDS, askLines, generalWait, queryOf } from "@/lib/askaround";
import { radiosBlockedReason, radiosNamed, radiosPathless } from "@/lib/sendon";

const { general, receiveOnly, send, lastError, now } = useDaemonContext();
const radios = useRadios();
const { told, allowsPath, byId, named, sharedPath } = radios;
const kind = usePersisted("ask.kind", GENERAL_KINDS[0] ?? "aprs", GENERAL_KINDS);
/** Ask around's Send on: its ticks and the radios the query goes on. */
const { ticks, radios: on, error: tickError, tick } = useSendOn("ask", radios);
/** The query's path, remembered by this browser apart from Local info's: one for all
 * radios. */
const request = useRequestPath("ask");
/** Whether the query has a path to set: some radio that is on may carry one (else no
 * fold), and one it goes on does (else greyed). */
const routable = computed(
  () => allowsPath.value && (on.value.length === 0 || on.value.some((radio) => radio.carriesPath)),
);
/** The path used when none is typed: the one the radios share; null while they differ. */
const usual = computed(() => sharedPath(on.value));
const refusal = ref("");

/** The wait of a kind is per radio; Ask waits for every radio the query would go on. */
const wait = computed(() =>
  generalWait(
    general.value,
    kind.value,
    on.value.map((radio) => radio.id),
    now.value,
  ),
);
/** Why nothing may go: no radio of it is connected, or none exist; undefined until radios are
 * known. */
const offline = computed(() => radiosBlockedReason(on.value, named, told.value));
/** Why Ask is off: "" while ticked for no radio that is on (the ticks show it), else the reason;
 * undefined when it may go. */
const why = computed(() => {
  const problem = routable.value ? request.problem.value : "";
  if (receiveOnly.value) return t("error.transmit.off");
  if (ticks.value.length > 0 && on.value.length === 0) return "";
  return (
    offline.value ??
    (problem !== "" ? problem : wait.value > 0 ? t("nearby.ask_wait", { seconds: wait.value }) : undefined)
  );
});
/** The two lines; the first names the radios the latest query went on where radios are named. */
const lines = computed(() => {
  const found = askLines(general.value, refusal.value, now.value);
  const name = found.refused ? "" : radiosNamed(general.value?.asked.at(-1)?.radios ?? [], byId, named);
  return name === "" ? found : { ...found, line: t("radio.line", { name, line: found.line }) };
});

watch(lastError, (toast) => {
  if (toast?.cmd === "general_query") refusal.value = errorReason(toast, radios);
});
watch(
  () => general.value?.asked.at(-1)?.at,
  () => (refusal.value = ""),
);

const asking = useCommandInFlight("general_query", () => general.value?.asked.at(-1)?.at);

function ask(): void {
  if (why.value !== undefined) return;
  refusal.value = "";
  asking.run(() =>
    send({
      cmd: "general_query",
      kind: kind.value,
      path: routable.value ? request.sent.value : null,
    }),
  );
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
        <option v-for="k in GENERAL_KINDS" :key="k" :value="k" :title="queryOf(k)">
          {{ t(`nearby.ask_kind.${k}`) }}
        </option>
      </select>
      <button
        type="button"
        class="btn"
        :disabled="why !== undefined || asking.busy.value"
        :title="why || t('nearby.ask_title', { query: queryOf(kind) })"
        @click="ask"
      >
        {{ t("nearby.ask_button") }}
      </button>
    </div>
    <SendOn v-if="ticks.length > 0" id="ask-send-on" :ticks="ticks" :error="tickError" @tick="tick" />
    <RequestPath
      v-if="allowsPath"
      v-model:path="request.path.value"
      :usual="usual"
      :problem="routable ? request.problem.value : ''"
      :disabled="!routable"
      :pathless="radiosPathless(on)"
    />
    <p class="ask-line" :class="lines.refused ? 'warn' : 'muted'" :title="lines.title || undefined">{{ lines.line }}</p>
    <p class="ask-line muted" :title="lines.countTitle || undefined">{{ lines.count }}</p>
  </fieldset>
</template>
