<script setup lang="ts">
// Local info (QRU), the last group box of the Objects tab (the stations that ask are answered with the objects that have a QRU group, the form's field; here we ask): **Ask** sends INFO to the stations near us (one request by radio only: the daemon sends it once, with RFONLY, at most one in a minute, and refuses it in RX only) with a distance in km that starts at the
// map's radius (empty: the servers' own). While several radios that can send are on, Send on stands under it (SendOn.vue, the beacon's row: a tick for each radio, `radio/<id>/local_info`, applied at once): the request goes once on each ticked radio that is connected, and the state word of the status line names the
// radios it went on ("FM, Mercury: Asked"). A server's row carries the tag of the radio it answered on, and its groups' buttons and Ask again go on that radio (a fact: it is where the server hears us); with one radio on there is no row, no tag and nothing is named. Ask is off while none of its radios is connected, with that as its reason. Under Send on the closed fold of the request's Path and
// RF only (RequestPath.vue, shared with Ask around; one fold for every radio, remembered by this browser for this box; there only while some radio that is on may carry a path, and greyed with its values kept while no ticked radio
// carries one; left as they are, an empty path and RF only ticked, the command carries neither and the request goes by the path of messages to QRU with RFONLY, as it always did); then the one status row of the groups (StatusFold): when the last request was sent and waiting for answers, then how many servers answered or that none did, or why it was refused. Ask is held for the minute,
// with the time left in its title, and while the path is wrong, with the reason. The servers that answered are a row each: its call, its groups as tags, by their plain names (the number of objects in each; a press asks that group, with the same distance) and under them, quiet, how many objects its closing line says it sent and how many arrived ("sent 1 · 1 arrived"; its closing line is the hover). Fewer than it sent, once the daemon has waited for late ones, is the warn colour with Ask again
// (the same request; it obeys the same waits as Ask). The objects themselves arrive as ordinary objects (the map, the Stations tab, where they carry the Local info tag); "in Stations" opens that tab and flashes the first of them.
import { computed, ref, watch } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import RequestPath from "@/components/RequestPath.vue";
import SendOn from "@/components/SendOn.vue";
import StatusFold from "@/components/StatusFold.vue";
import TagMark from "@/components/TagMark.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useCommandInFlight } from "@/composables/useInFlight";
import { useRadios } from "@/composables/useRadios";
import { useRequestPath } from "@/composables/useRequestPath";
import { useSendOn } from "@/composables/useSendOn";
import { PREFS_RADIO } from "@/composables/useStationRadio";
import { t } from "@/i18n";
import { errorReason } from "@/i18n/errortext";
import { attend } from "@/lib/attention";
import { radioTone } from "@/lib/channels";
import { effectivePath } from "@/lib/messages";
import { askWait, kmWrong, qruLook, requestText, sentLine } from "@/lib/qru";
import { categoryLabel, groupName } from "@/lib/qrucategories";
import { sharedPath, type PageRadio } from "@/lib/radios";
import { radiosBlockedReason, radiosNamed, radiosPathless } from "@/lib/sendon";
import { stationRowId } from "@/lib/stations";
import { LIMITS } from "@/protocol/lists";
import type { Command, QruServer } from "@/protocol/protocol";

const { qru, receiveOnly, send, config, lastError, now, panel, prefs } = useDaemonContext();
const radios = useRadios();
const { told, severalSenders: several, senders, allowsPath, byId, named, pathOf } = radios;
/** Local info's Send on: its ticks, and the radios the request INFO goes on as they stand. */
const { ticks, radios: on, error: tickError, tick } = useSendOn("local_info", radios);
/** The path and RF only of a request, remembered by this browser apart from Ask around's: one for every radio. */
const request = useRequestPath("qru");
/** Whether a request on these radios has a path and RF only to set: some radio that is on may carry one (else the fold is not there), and one of these does (else it is greyed). */
const routable = (to: readonly PageRadio[]): boolean => allowsPath.value && (to.length === 0 || to.some((radio) => radio.carriesPath));
/** The path a request goes by on a radio when none is typed: on radio 1 the one set for the station QRU (the topic `station_prefs`), else the radio's own. */
const qruPath = (radio: PageRadio): string => (radio.id === PREFS_RADIO ? effectivePath(prefs.paths.value, pathOf(radio), "QRU").text : pathOf(radio));
/** The path the request INFO goes by with none typed: the one its radios share; null while theirs differ. */
const usual = computed(() => sharedPath(on.value, qruPath));
const typed = ref<string | null>(null); // (what the person typed; null until then, and the field is the map's radius)
const km = computed({
  get: () => typed.value ?? config.value?.values["map/radius_km"] ?? "",
  set: (text: string) => (typed.value = text),
});
const wrong = computed(() => kmWrong(km.value));
const servers = computed(() => qru.value?.servers ?? []);
/** The radio a server answered on, while it is on and can send: where a request to it goes; null for none (the request then goes on the ticked radios). */
const radioOf = (server: QruServer): PageRadio | null => senders.value.find((radio) => radio.id === server.radio) ?? null;
/** The radios a request to a server goes on: the one it answered on, else those of Send on. */
const toServer = (server: QruServer): readonly PageRadio[] => {
  const one = radioOf(server);
  return one === null ? on.value : [one];
};
/** Each server with what its row says of the objects it sent, and the radio it answered on where a radio is named (its tag). */
const rows = computed(() =>
  servers.value.map((server) => {
    const answered = server.radio === null || !named(server.radio) ? undefined : byId(server.radio);
    return { server, line: sentLine(server, now.value), answered };
  }),
);
const asked = computed(() => qru.value?.asked ?? null);
/** The seconds before the request may go on the radios: the waits are each radio's (the topic tells the last request, with its radios), and a request waits for every radio it would go on. */
const waitOn = (to: readonly PageRadio[], text: string | null): number => {
  const last = asked.value;
  const theirs = last !== null && (last.radios.length === 0 || to.length === 0 || to.some((radio) => last.radios.includes(radio.id)));
  return askWait(theirs ? last : null, now.value, text);
};
const refusal = ref(""); // (why the daemon refused the last request, until the next one)
const look = computed(() => {
  const found = qruLook(asked.value, servers.value, refusal.value, now.value);
  const name = refusal.value !== "" ? "" : radiosNamed(asked.value?.radios ?? [], byId, named);
  return found === null || name === "" ? found : { ...found, state: t("radio.line", { name, line: found.state }) };
});
/** Why a request on the radios that waits `seconds` may not go, or undefined when it may (RX only, the radios, the path, its wait); "" while it goes on no radio that is on (ticked nowhere: the row of ticks shows it). */
const heldBy = (to: readonly PageRadio[], seconds: number): string | undefined => {
  const problem = routable(to) ? request.problem.value : "";
  return receiveOnly.value
    ? t("error.transmit.off")
    : several.value && to.length === 0
      ? ""
      : (radiosBlockedReason(to, named, told.value) ?? (problem !== "" ? problem : seconds > 0 ? t("objects.qru_wait", { seconds }) : undefined));
};
const why = computed(() => heldBy(on.value, waitOn(on.value, requestText("INFO", km.value))));
/** Why a group's button is off, or undefined when it may be pressed (RX only, the server's radio, the path, or its own wait). */
const groupWhy = (server: QruServer, word: string): string | undefined => heldBy(toServer(server), waitOn(toServer(server), requestText(word, km.value)));

/** A request in flight: no button sends another until the daemon has told it or refused it. */
const asking = useCommandInFlight("qru_ask", () => asked.value?.at);

watch(lastError, (toast) => {
  if (toast?.cmd === "qru_ask") refusal.value = errorReason(toast, radios);
});
watch(
  () => asked.value?.at,
  () => (refusal.value = ""),
);

/** The request as the command carries it: the text, the path and RF only only when the fold says other than the usual (an empty path and RF only ticked: the path of messages to QRU with RFONLY), and the one radio of a
 * request to a server while several are on (none: the radios of Send on). */
function command(text: string, to: readonly PageRadio[], one: PageRadio | null): Command {
  const radio = several.value && one !== null ? { radio: one.id } : {};
  return !routable(to) || (request.sent.value === null && request.rfOnly.value)
    ? { cmd: "qru_ask", text, ...radio }
    : { cmd: "qru_ask", text, path: request.sent.value, rf_only: request.rfOnly.value, ...radio };
}

/** Sends the request for INFO with the distance of the field on the radios of Send on, unless it is held (RX only, the radios, the path, or its wait). */
function ask(): void {
  const text = requestText("INFO", km.value);
  if (text === null || why.value !== undefined) return;
  refusal.value = "";
  asking.run(() => send(command(text, on.value, null)));
}

/** Sends the request for a group of a server, with the distance of the field, on the radio the server answered on, unless it is held (a group may go ten seconds after INFO, whose minute is not its own). */
function askGroup(server: QruServer, word: string): void {
  const text = requestText(word, km.value);
  if (text === null || groupWhy(server, word) !== undefined) return;
  refusal.value = "";
  asking.run(() => send(command(text, toServer(server), radioOf(server))));
}

/** Why Ask again is off (RX only, the server's radio, the path, or the wait for that request), or undefined when it may be pressed. */
const againWhy = (server: QruServer, text: string): string | undefined => heldBy(toServer(server), waitOn(toServer(server), text));

/** The same request once more, as it went (its own distance, not the field's), on the radio the server answered on. */
function again(server: QruServer, text: string): void {
  if (againWhy(server, text) !== undefined) return;
  refusal.value = "";
  asking.run(() => send(command(text, toServer(server), radioOf(server))));
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
      <button type="button" class="btn" :disabled="why !== undefined || wrong || asking.busy.value" :title="why || undefined" @click="ask">
        {{ t("objects.qru_ask") }}
      </button>
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
        @keydown.enter="ask"
      />
      <InfoTip :label="t('settings.about', { label: t('objects.qru_km_label') })">{{ t("objects.qru_km_tip") }}</InfoTip>
    </div>
    <SendOn v-if="ticks.length > 0" id="qru-send-on" :ticks="ticks" :error="tickError" @tick="tick" />
    <RequestPath
      v-if="allowsPath"
      v-model:path="request.path.value"
      v-model:rf-only="request.rfOnly.value"
      :usual="usual"
      :problem="routable(on) ? request.problem.value : ''"
      :disabled="!routable(on)"
      :pathless="radiosPathless(on)"
    />
    <StatusFold v-if="look" class="qrustatus" :state="look.state" :tone="look.tone" :line="look.line">
      <template v-if="asked" #default>
        <p class="igatefold">{{ t("objects.qru_request", { text: asked.text }) }}</p>
      </template>
    </StatusFold>
    <ul v-if="servers.length > 0" class="qru-servers" :aria-label="t('objects.qru')">
      <li v-for="{ server, line, answered } in rows" :key="server.call" class="qru-server">
        <span class="qru-call"
          ><span class="mono strong">{{ server.call }}</span
          ><TagMark v-if="answered" :tone="radioTone(answered)" :title="t('radio.heard_on', { name: answered.name })">{{ answered.name }}</TagMark></span
        >
        <span class="qru-groups">
          <button
            v-for="group in server.groups"
            :key="group.name"
            type="button"
            class="btn small qru-group"
            :disabled="groupWhy(server, group.name) !== undefined || wrong || asking.busy.value"
            :title="groupWhy(server, group.name) || t('objects.qru_group', { server: server.call, group: groupName(group.name) })"
            @click="askGroup(server, group.name)"
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
            :disabled="againWhy(server, line.again) !== undefined || asking.busy.value"
            :title="againWhy(server, line.again) || t('objects.qru_again_title', { server: server.call, request: line.again })"
            @click="again(server, line.again)"
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
