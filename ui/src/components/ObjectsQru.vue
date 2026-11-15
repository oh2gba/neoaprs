<script setup lang="ts">
// Local info (QRU), the last group box of the Objects tab (the stations that ask are answered with the objects that have a QRU group, the form's field; here we ask): **Ask** sends INFO to the stations near us (one request by radio only: the daemon sends it once, with RFONLY, at most one in a minute, and refuses it in RX only) with a distance in km that starts at the
// map's radius (empty: the servers' own). It goes on one radio (plan rule 3.6): while more than one is on, the radio is chosen in front of Ask, as in Ask around (the main radio first; chosen at the start unless a request is kept, and following each request to its radio), the state word of the status line says the radio the request went on ("HF: Asked"), and
// Ask again and a group's button go on that radio; with one radio on there is no choice and nothing is named. Ask is off while its radio is not connected, with that as its reason. Under it the closed fold of the request's Path and
// RF only (RequestPath.vue, shared with Ask around; remembered by this browser for this box and for each radio apart; there only while some radio that is on may carry a path, and greyed with its values kept while the radio chosen
// carries none; left as they are, an empty path and RF only ticked, the command carries neither and the request goes by the path of messages to QRU with RFONLY, as it always did); then the one status row of the groups (StatusFold): when the last request was sent and waiting for answers, then how many servers answered or that none did, or why it was refused. Ask is held for the minute,
// with the time left in its title, and while the path is wrong, with the reason. The servers that answered are a row each: its call, its groups as tags, by their plain names (the number of objects in each; a press asks that group, with the same distance) and under them, quiet, how many objects its closing line says it sent and how many arrived ("sent 1 · 1 arrived"; its closing line is the hover). Fewer than it sent, once the daemon has waited for late ones, is the warn colour with Ask again
// (the same request; it obeys the same waits as Ask). The objects themselves arrive as ordinary objects (the map, the Stations tab, where they carry the Local info tag); "in Stations" opens that tab and flashes the first of them.
import { computed, effectScope, ref, watch } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import RequestPath from "@/components/RequestPath.vue";
import StatusFold from "@/components/StatusFold.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { useRequestPath, type RequestPath as Request } from "@/composables/useRequestPath";
import RadioPick from "@/components/RadioPick.vue";
import { t } from "@/i18n";
import { errorReason } from "@/i18n/errortext";
import { attend } from "@/lib/attention";
import { radioBlockedReason } from "@/lib/compose";
import { effectivePath } from "@/lib/messages";
import { askWait, kmWrong, qruLook, requestText, sentLine } from "@/lib/qru";
import { categoryLabel, groupName } from "@/lib/qrucategories";
import type { RadioId } from "@/lib/radios";
import { stationRowId } from "@/lib/stations";
import { LIMITS } from "@/protocol/lists";
import type { Command } from "@/protocol/protocol";

const { qru, receiveOnly, send, config, lastError, now, panel, prefs, fallbackPath } = useDaemonContext();
const radios = useRadios();
const { told, severalSenders: several, enabled, allowsPath, byId, named, choose } = radios;
/** The radio chosen beside Ask (`picked`, null: the main radio), the one it goes on, and the radios to choose from, the main radio first (useRadios `choose`). */
const { picked, radio, choices } = choose();

/** The path and RF only of each radio, remembered by this browser apart: radio 1, the FM radio of before, keeps what this browser kept before the radios had ids. */
const scope = effectScope(); // (the pane's own: it ends with the pane)
const requests = new Map<RadioId | null, Request>();
function requestOn(id: RadioId | null): Request {
  let request = requests.get(id);
  if (request === undefined) {
    const key = id === null || id === 1 ? "qru" : `qru.${id}`;
    request = scope.run(() => useRequestPath(key)) ?? useRequestPath(key);
    requests.set(id, request);
  }
  return request;
}
const request = computed(() => requestOn(radio.value));
/** Whether a request on the radio has a path and RF only to set: some radio that is on may carry one (else the fold is not there), and this one does (else it is greyed). */
const routable = (id: RadioId | null): boolean => allowsPath.value && (id === null || byId(id)?.carriesPath !== false);
/** Why the fold is greyed on that radio, as Route says it ("HF: no path"). */
const pathless = (id: RadioId | null): string | undefined => (id === null ? undefined : t("radio.no_path", { name: byId(id)?.name ?? "" }));
/** The path a request goes by when none is typed: the one set for the station QRU, else the beacon's. */
const usual = computed(() => effectivePath(prefs.paths.value, fallbackPath.value, "QRU").text);
const typed = ref<string | null>(null); // (what the person typed; null until then, and the field is the map's radius)
const km = computed({
  get: () => typed.value ?? config.value?.values["map/radius_km"] ?? "",
  set: (text: string) => (typed.value = text),
});
const wrong = computed(() => kmWrong(km.value));
const servers = computed(() => qru.value?.servers ?? []);
/** Each server with what its row says of the objects it sent. */
const rows = computed(() => servers.value.map((server) => ({ server, line: sentLine(server, now.value) })));
const asked = computed(() => qru.value?.asked ?? null);
/** The radio a request already sent goes on again (Ask again, a group's button): the one it went on while that is on, else the one chosen. */
const againOn = computed(() => {
  const went = asked.value?.radio ?? null;
  return went !== null && enabled.value.some((r) => r.id === went) ? went : radio.value;
});
/** The seconds before the request may go on the radio: the waits are that radio's (the topic tells the last request, with its radio). */
const waitOn = (id: RadioId | null, text: string | null): number => {
  const last = asked.value;
  return askWait(last !== null && (last.radio === null || id === null || last.radio === id) ? last : null, now.value, text);
};
const waitFor = (word: string): number => waitOn(againOn.value, requestText(word, km.value));
const wait = computed(() => waitOn(radio.value, requestText("INFO", km.value)));
const refusal = ref(""); // (why the daemon refused the last request, until the next one)
const look = computed(() => {
  const found = qruLook(asked.value, servers.value, refusal.value, now.value);
  const went = asked.value?.radio ?? null;
  const name = went === null || refusal.value !== "" || !named(went) ? undefined : byId(went)?.name;
  return found === null || name === undefined ? found : { ...found, state: t("radio.line", { name, line: found.state }) };
});
/** Why nothing may go on the radio: it is not connected (named where several are on), or there is none; undefined before the daemon has told its radios. */
const offline = (id: RadioId | null): string | undefined => {
  const on = id === null ? undefined : byId(id);
  return radioBlockedReason(on, on !== undefined && named(on.id), told.value);
};
/** Why a request on the radio that waits `seconds` may not go, or undefined when it may (RX only, the radio, the path, its wait). */
const heldBy = (id: RadioId | null, seconds: number): string | undefined => {
  const problem = routable(id) ? requestOn(id).problem.value : "";
  return receiveOnly.value
    ? t("error.transmit.off")
    : (offline(id) ?? (problem !== "" ? problem : seconds > 0 ? t("objects.qru_wait", { seconds }) : undefined));
};
const why = computed(() => heldBy(radio.value, wait.value));
/** Why a group's button is off, or undefined when it may be pressed (RX only, the radio, the path, or its own wait). */
const groupWhy = (word: string): string | undefined => heldBy(againOn.value, waitFor(word));

watch(lastError, (toast) => {
  if (toast?.cmd === "qru_ask") refusal.value = errorReason(toast, radios);
});
watch(
  () => asked.value?.at,
  () => (refusal.value = ""),
);
/** The choice follows each request (and the one kept when the pane opens) to its radio while that is on, so that the fold in sight is the one a group's button and Ask again go by (a choice that goes off is forgotten: useRadios `choose`). */
watch(
  () => [asked.value?.at, told.value],
  () => {
    const went = asked.value?.radio ?? null;
    if (went !== null && enabled.value.some((r) => r.id === went)) picked.value = went;
  },
  { immediate: true },
);

/** The request as the command carries it: the text, the path and RF only only when the fold says other than the usual (an empty path and RF only ticked: the path of messages to QRU with RFONLY), and the radio while several are on. */
function command(text: string, id: RadioId | null): Command {
  const fold = requestOn(id);
  const on = several.value && id !== null ? { radio: id } : {};
  return !routable(id) || (fold.sent.value === null && fold.rfOnly.value)
    ? { cmd: "qru_ask", text, ...on }
    : { cmd: "qru_ask", text, path: fold.sent.value, rf_only: fold.rfOnly.value, ...on };
}

/** Sends the request for INFO with the distance of the field on the radio chosen, or for a group on the radio of the request it answers, unless that request is held (RX only, the radio, the path, or its own wait: a group may go ten seconds after INFO, whose minute is not its own). */
function ask(word: string): void {
  const text = requestText(word, km.value);
  const id = word === "INFO" ? radio.value : againOn.value;
  if (text === null || (word === "INFO" ? why.value : groupWhy(word)) !== undefined) return;
  refusal.value = "";
  send(command(text, id));
}

/** Why Ask again is off (RX only, the radio, the path, or the wait for that request), or undefined when it may be pressed. */
const againWhy = (text: string): string | undefined => heldBy(againOn.value, waitOn(againOn.value, text));

/** The same request once more, as it went (its own distance, not the field's), on its radio by the path of that radio's fold. */
function again(text: string): void {
  if (againWhy(text) !== undefined) return;
  refusal.value = "";
  send(command(text, againOn.value));
}

/** The Stations tab, with the row of the first of the objects that arrived flashed. */
function inStations(names: readonly string[]): void {
  panel.show("stations");
  const [first] = names;
  if (first !== undefined) void attend(stationRowId(first));
}
</script>

<template>
  <fieldset class="objects-qru">
    <legend class="qru-head">
      {{ t("objects.qru") }} <span v-if="servers.length > 0" class="muted">{{ servers.length }}</span>
      <InfoTip :label="t('objects.qru_tip_label')" picture="qru">
        <span class="info-line">{{ t("objects.qru_tip") }}</span>
      </InfoTip>
    </legend>
    <div class="qru-ask">
      <RadioPick v-if="several" class="qru-radio" :radio="radio" :choices="choices" @pick="picked = $event" />
      <button type="button" class="btn" :disabled="why !== undefined || wrong" :title="why" @click="ask('INFO')">{{ t("objects.qru_ask") }}</button>
      <input
        v-model="km"
        class="input mono qru-km"
        :class="{ invalid: wrong }"
        type="text"
        inputmode="numeric"
        autocomplete="off"
        :maxlength="String(LIMITS.qru.kmMax).length"
        :placeholder="t('objects.qru_km')"
        :aria-label="t('objects.qru_km_label')"
        @keydown.enter="ask('INFO')"
      />
      <InfoTip :label="t('settings.about', { label: t('objects.qru_km_label') })">{{ t("objects.qru_km_tip") }}</InfoTip>
    </div>
    <RequestPath
      v-if="allowsPath"
      v-model:path="request.path.value"
      v-model:rf-only="request.rfOnly.value"
      :usual="usual"
      :problem="routable(radio) ? request.problem.value : ''"
      :disabled="!routable(radio)"
      :pathless="pathless(radio)"
    />
    <StatusFold v-if="look" class="qrustatus" :state="look.state" :tone="look.tone" :line="look.line">
      <template v-if="asked" #default>
        <p class="igatefold">{{ t("objects.qru_request", { text: asked.text }) }}</p>
      </template>
    </StatusFold>
    <ul v-if="servers.length > 0" class="qru-servers" :aria-label="t('objects.qru')">
      <li v-for="{ server, line } in rows" :key="server.call" class="qru-server">
        <span class="mono strong qru-call">{{ server.call }}</span>
        <span class="qru-groups">
          <button
            v-for="group in server.groups"
            :key="group.name"
            type="button"
            class="btn small qru-group"
            :disabled="groupWhy(group.name) !== undefined || wrong"
            :title="groupWhy(group.name) ?? t('objects.qru_group', { server: server.call, group: groupName(group.name) })"
            @click="ask(group.name)"
          >
            {{ categoryLabel(group.name) }}{{ " " }}<span class="qru-count">{{ group.count }}</span>
          </button>
        </span>
        <span v-if="line" class="qru-sent" :class="line.warn ? 'warn' : 'muted'" :title="line.warn ? t('objects.qru_lost_title') : server.sent">
          {{ line.text }}
          <button
            v-if="line.again"
            type="button"
            class="btn small qru-again"
            :disabled="againWhy(line.again) !== undefined"
            :title="againWhy(line.again) ?? t('objects.qru_again_title', { server: server.call, request: line.again })"
            @click="again(line.again)"
          >
            {{ t("objects.qru_again") }}
          </button>
          <button v-if="server.received.length > 0" type="button" class="linkbutton qru-stations" @click="inStations(server.received)">
            {{ t("objects.qru_in_stations", { tab: t("tab.stations") }) }}
          </button>
        </span>
      </li>
    </ul>
  </fieldset>
</template>
