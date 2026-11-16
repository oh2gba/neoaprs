<script setup lang="ts">
// Ask around, the first box of the Nearby tab: one general query of APRS sent to the stations in radio range (the daemon's services/generalask.py), chosen in plain words (Who is around ?APRS?, iGates ?IGATE?, Weather stations ?WX?,
// each with its query in its hover title), and **Ask**. Under it, while several radios that can send are on, Send on (SendOn.vue, the beacon's row: a tick for each radio, `radio/<id>/ask`, applied at once),
// then the closed fold of the request's Path and RF only (RequestPath.vue; one fold for every radio: empty is each radio's own path; remembered by this browser for this box apart from
// Local info's; its placeholder the path its radios share, else the page's word for the default; there only while some radio that is on may carry a path, and greyed with its values kept while no ticked radio carries one), then two quiet lines of a height that is always kept, so that nothing moves when
// their words change: what was asked, when and by what path, and that the answers arrive on the map and in Stations (before a query what Ask does, after a refusal the reason), and how many stations that had been quiet for
// ten minutes spoke in the two minutes after (their calls in the hover; they are likely answers, and the line does not say more). The query goes once on each ticked radio that is connected; the first line names the radios the
// latest query went on while several are on, and with one radio on there is no row and nothing is named. Ask is off, with the reason in its title, in RX only, while none of its radios is connected, while the path is wrong,
// and for the minute after a query of the same kind on one of its radios.
import { computed, ref, watch } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import RequestPath from "@/components/RequestPath.vue";
import SendOn from "@/components/SendOn.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
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
/** Ask around's Send on: its ticks, and the radios the query goes on as they stand. */
const { ticks, radios: on, error: tickError, tick } = useSendOn("ask", radios);
/** The path and RF only of the query, remembered by this browser apart from Local info's: one for every radio. */
const request = useRequestPath("ask");
/** Whether the query has a path and RF only to set: some radio that is on may carry one (else the fold is not there), and one of those it goes on does (else it is greyed). */
const routable = computed(() => allowsPath.value && (on.value.length === 0 || on.value.some((radio) => radio.carriesPath)));
/** The path the query goes by with none typed: the one its radios share (each goes by its own); null while theirs differ. */
const usual = computed(() => sharedPath(on.value));
const refusal = ref(""); // (why the daemon refused the last Ask, until the next query)

/** The wait of a kind is each radio's, and Ask waits for every radio the query would go on. */
const wait = computed(() =>
  generalWait(
    general.value,
    kind.value,
    on.value.map((radio) => radio.id),
    now.value,
  ),
);
/** Why nothing may go: none of its radios is connected (named where several are on), or there is none; undefined before the daemon has told its radios. */
const offline = computed(() => radiosBlockedReason(on.value, named, told.value));
/** Why Ask is off: "" while it is ticked for no radio that is on (the row of ticks shows it), else the reason; undefined while it may go. */
const why = computed(() => {
  const problem = routable.value ? request.problem.value : "";
  if (receiveOnly.value) return t("error.transmit.off");
  if (ticks.value.length > 0 && on.value.length === 0) return "";
  return offline.value ?? (problem !== "" ? problem : wait.value > 0 ? t("nearby.ask_wait", { seconds: wait.value }) : undefined);
});
/** The two lines; the first names the radios the latest query went on where a radio is named. */
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

function ask(): void {
  if (why.value !== undefined) return;
  refusal.value = "";
  send({ cmd: "general_query", kind: kind.value, path: routable.value ? request.sent.value : null, rf_only: request.rfOnly.value });
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
      <button type="button" class="btn" :disabled="why !== undefined" :title="why || t('nearby.ask_title', { query: queryOf(kind) })" @click="ask">
        {{ t("nearby.ask_button") }}
      </button>
    </div>
    <SendOn v-if="ticks.length > 0" id="ask-send-on" :ticks="ticks" :error="tickError" @tick="tick" />
    <RequestPath
      v-if="allowsPath"
      v-model:path="request.path.value"
      v-model:rf-only="request.rfOnly.value"
      :usual="usual"
      :problem="routable ? request.problem.value : ''"
      :disabled="!routable"
      :pathless="radiosPathless(on)"
    />
    <p class="ask-line" :class="lines.refused ? 'warn' : 'muted'" :title="lines.title || undefined">{{ lines.line }}</p>
    <p class="ask-line muted" :title="lines.countTitle || undefined">{{ lines.count }}</p>
  </fieldset>
</template>
