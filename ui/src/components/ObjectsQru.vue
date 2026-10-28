<script setup lang="ts">
// Local info (QRU), the last group box of the Objects tab (the stations that ask are answered with the objects that have a QRU group, the form's field; here we ask): **Ask** sends INFO to the stations near us (one request by radio only: the daemon sends it once, with RFONLY, at most one in a minute, and refuses it in RX only) with a distance in km that starts at the
// map's radius (empty: the servers' own), and under it the closed fold of the request's Path and RF only (RequestPath.vue, shared with Ask around; remembered by this browser for this box apart; left as they are, an empty path and RF only
// ticked, the command carries neither and the request goes by the path of messages to QRU with RFONLY, as it always did); then the one status row of the groups (StatusFold): when the last request was sent and waiting for answers, then how many servers answered or that none did, or why it was refused. Ask is held for the minute,
// with the time left in its title, and while the path is wrong, with the reason. The servers that answered are a row each: its call, its groups as tags, by their plain names (the number of objects in each; a press asks that group, with the same distance) and under them, quiet, how many objects its closing line says it sent and how many arrived ("sent 1 · 1 arrived"; its closing line is the hover). Fewer than it sent, once the daemon has waited for late ones, is the warn colour with Ask again
// (the same request; it obeys the same waits as Ask). The objects themselves arrive as ordinary objects (the map, the Stations tab, where they carry the Local info tag); "in Stations" opens that tab and flashes the first of them.
import { computed, ref, watch } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import RequestPath from "@/components/RequestPath.vue";
import StatusFold from "@/components/StatusFold.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRequestPath } from "@/composables/useRequestPath";
import { t } from "@/i18n";
import { errorReason } from "@/i18n/errortext";
import { attend } from "@/lib/attention";
import { effectivePath } from "@/lib/messages";
import { askWait, kmWrong, qruLook, requestText, sentLine } from "@/lib/qru";
import { categoryLabel, groupName } from "@/lib/qrucategories";
import { stationRowId } from "@/lib/stations";
import { LIMITS } from "@/protocol/lists";
import type { Command } from "@/protocol/protocol";

const { qru, receiveOnly, send, config, lastError, now, panel, prefs, fallbackPath } = useDaemonContext();
const request = useRequestPath("qru");
const { path, rfOnly, problem } = request;
/** The path a request goes by when none is typed: the one set for the station QRU, else the beacon's. */
const usual = computed(() => effectivePath(prefs.paths.value, fallbackPath.value, "QRU").text || t("route.direct"));
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
const waitFor = (word: string): number => askWait(asked.value, now.value, requestText(word, km.value));
const wait = computed(() => waitFor("INFO"));
const refusal = ref(""); // (why the daemon refused the last request, until the next one)
const look = computed(() => qruLook(asked.value, servers.value, refusal.value, now.value));
/** Why a request that waits `seconds` may not go, or undefined when it may (RX only, the path, its wait). */
const heldBy = (seconds: number): string | undefined =>
  receiveOnly.value ? t("pill.rx_send") : problem.value !== "" ? problem.value : seconds > 0 ? t("objects.qru_wait", { seconds }) : undefined;
const why = computed(() => heldBy(wait.value));
/** Why a group's button is off, or undefined when it may be pressed (RX only, the path, or its own wait). */
const groupWhy = (word: string): string | undefined => heldBy(waitFor(word));

watch(lastError, (toast) => {
  if (toast?.cmd === "qru_ask") refusal.value = errorReason(toast);
});
watch(
  () => asked.value?.at,
  () => (refusal.value = ""),
);

/** The request as the command carries it: the text, and the path and RF only only when the fold says other than the usual (an empty path and RF only ticked: the path of messages to QRU with RFONLY). */
function command(text: string): Command {
  return request.sent.value === null && rfOnly.value ? { cmd: "qru_ask", text } : { cmd: "qru_ask", text, path: request.sent.value, rf_only: rfOnly.value };
}

/** Sends the request for the word (INFO or a group) with the distance of the field, unless that request is held (RX only, the path, or its own wait: a group may go ten seconds after INFO, whose minute is not its own). */
function ask(word: string): void {
  const text = requestText(word, km.value);
  if (text === null || groupWhy(word) !== undefined) return;
  refusal.value = "";
  send(command(text));
}

/** Why Ask again is off (RX only, the path, or the wait for that request), or undefined when it may be pressed. */
const againWhy = (text: string): string | undefined => heldBy(askWait(asked.value, now.value, text));

/** The same request once more, as it went (its own distance, not the field's), by the path of the fold. */
function again(text: string): void {
  if (againWhy(text) !== undefined) return;
  refusal.value = "";
  send(command(text));
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
    <RequestPath v-model:path="path" v-model:rf-only="rfOnly" :placeholder="usual" :problem="problem" />
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
