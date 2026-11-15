<script setup lang="ts">
// Ask around, the first box of the Nearby tab: one general query of APRS sent to the stations in radio range (the daemon's services/generalask.py), chosen in plain words (Who is around ?APRS?, iGates ?IGATE?, Weather stations ?WX?,
// each with its query in its hover title), and **Ask**. Under it the closed fold of the request's Path and RF only (RequestPath.vue; empty is the beacon's path, which the placeholder shows; remembered by this browser for this
// box apart from Local info's), then two quiet lines of a height that is always kept, so that nothing moves when their words change: what was asked, when and by what path, and that the answers arrive on the map and in Stations
// (before a query what Ask does, after a refusal the reason), and how many stations that had been quiet for ten minutes spoke in the two minutes after (their calls in the hover; they are likely answers, and the line does not say
// more). The query goes on one radio (plan rule 3.6): while more than one is on, the radio is chosen beside Ask (the main radio first and at the start) and the first line says the radio the latest query went on; with one radio on there is
// no choice and nothing is named. The fold is there only while some radio that is on may carry a path, greyed with its values kept while the radio chosen carries none, and remembered for each radio apart. Ask is off, with the reason
// in its title, in RX only, while its radio is not connected, while the path is wrong, and for the minute after a query of the same kind on that radio.
import { computed, effectScope, ref, watch } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import RequestPath from "@/components/RequestPath.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { usePersisted } from "@/composables/usePersisted";
import { useRadios } from "@/composables/useRadios";
import { useRequestPath, type RequestPath as Request } from "@/composables/useRequestPath";
import RadioPick from "@/components/RadioPick.vue";
import { t } from "@/i18n";
import { errorReason } from "@/i18n/errortext";
import { GENERAL_KINDS, askLines, generalWait, queryOf } from "@/lib/askaround";
import { radioBlockedReason } from "@/lib/compose";
import type { RadioId } from "@/lib/radios";

const { general, receiveOnly, send, lastError, now, fallbackPath } = useDaemonContext();
const radios = useRadios();
const { told, several, allowsPath, byId, named, choose } = radios;
const kind = usePersisted("ask.kind", GENERAL_KINDS[0] ?? "aprs", GENERAL_KINDS);
/** The radio chosen beside Ask (`picked`, null: the main radio), the one it goes on, and the radios to choose from, the main radio first (useRadios `choose`). */
const { picked, radio, choices } = choose();
/** The path and RF only of each radio, remembered by this browser apart from Local info's: radio 1, the FM radio of before, keeps what this browser kept before the radios had ids. */
const scope = effectScope(); // (the pane's own: it ends with the pane)
const requests = new Map<RadioId | null, Request>();
const request = computed(() => {
  const id = radio.value;
  let found = requests.get(id);
  if (found === undefined) {
    const key = id === null || id === 1 ? "ask" : `ask.${id}`;
    found = scope.run(() => useRequestPath(key)) ?? useRequestPath(key);
    requests.set(id, found);
  }
  return found;
});
/** Whether the query has a path and RF only to set: some radio that is on may carry one (else the fold is not there), and the one chosen does (else it is greyed). */
const routable = computed(() => allowsPath.value && (radio.value === null || byId(radio.value)?.carriesPath !== false));
const refusal = ref(""); // (why the daemon refused the last Ask, until the next query)

/** The wait of a kind is that radio's: the last query of each kind on it. */
const onRadio = computed(() => {
  const state = general.value;
  const id = radio.value;
  return state === null || id === null ? state : { asked: state.by_radio.filter((a) => a.radio === null || a.radio === id), by_radio: [] };
});
const wait = computed(() => generalWait(onRadio.value, kind.value, now.value));
/** Why nothing may go on the radio: it is not connected (named where several are on), or there is none; undefined before the daemon has told its radios. */
const offline = computed(() => {
  const on = radio.value === null ? undefined : byId(radio.value);
  return radioBlockedReason(on, on !== undefined && named(on.id), told.value);
});
const why = computed(() => {
  const problem = routable.value ? request.value.problem.value : "";
  if (receiveOnly.value) return t("pill.rx_send");
  return offline.value ?? (problem !== "" ? problem : wait.value > 0 ? t("nearby.ask_wait", { seconds: wait.value }) : undefined);
});
/** The two lines; the first says the radio the latest query went on where a radio is named. */
const lines = computed(() => {
  const found = askLines(general.value, refusal.value, now.value);
  const went = general.value?.asked.at(-1)?.radio ?? null;
  const name = went === null || found.refused || !named(went) ? undefined : byId(went)?.name;
  return name === undefined ? found : { ...found, line: t("radio.line", { name, line: found.line }) };
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
  const fold = request.value;
  const on = several.value && radio.value !== null ? { radio: radio.value } : {};
  send({ cmd: "general_query", kind: kind.value, path: routable.value ? fold.sent.value : null, rf_only: fold.rfOnly.value, ...on });
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
      <RadioPick v-if="several" class="ask-radio" :radio="radio" :choices="choices" @pick="picked = $event" />
      <button type="button" class="btn" :disabled="why !== undefined" :title="why ?? t('nearby.ask_title', { query: queryOf(kind) })" @click="ask">
        {{ t("nearby.ask_button") }}
      </button>
    </div>
    <RequestPath
      v-if="allowsPath"
      v-model:path="request.path.value"
      v-model:rf-only="request.rfOnly.value"
      :usual="fallbackPath"
      :problem="routable ? request.problem.value : ''"
      :disabled="!routable"
      :pathless="radio === null ? undefined : t('radio.no_path', { name: byId(radio)?.name ?? '' })"
    />
    <p class="ask-line" :class="lines.refused ? 'warn' : 'muted'" :title="lines.title || undefined">{{ lines.line }}</p>
    <p class="ask-line muted" :title="lines.countTitle || undefined">{{ lines.count }}</p>
  </fieldset>
</template>
