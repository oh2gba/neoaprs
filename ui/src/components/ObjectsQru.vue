<script setup lang="ts">
// Local info (QRU), the last group box of the Objects tab. **Ask** sends INFO to the stations
// near us (the daemon sends it once with RFONLY, at most once a minute, and refuses it in RX
// only) with a distance in km starting at the map's radius. While several sending radios are on,
// Send on follows (SendOn.vue, `radio/<id>/local_info`): the request goes once on each ticked
// connected radio. A server's row carries the tag of the radio it answered on, and its group
// buttons and Ask again use that radio. Under Send on is the closed fold of the request's Path
// and RF only (RequestPath.vue, shared with Ask around). One status row (StatusFold) follows,
// then a row per answering server with its groups as tags and how many objects it sent and how
// many arrived. The objects arrive as ordinary objects (map, Stations tab with the Local info
// tag).
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
/** Local info's Send on: its ticks and the radios INFO goes on. */
const { ticks, radios: on, error: tickError, tick } = useSendOn("local_info", radios);
/** A request's path and RF only, remembered by this browser apart from Ask around's: one for all
 * radios. */
const request = useRequestPath("qru");
/** Whether a request on these radios has a path and RF only to set: some radio that is on may
 * carry one (else no fold), and one of these does (else greyed). */
const routable = (to: readonly PageRadio[]): boolean =>
  allowsPath.value && (to.length === 0 || to.some((radio) => radio.carriesPath));
/** The path a request uses on a radio when none is typed: on radio 1 the one set for the station
 * QRU (topic `station_prefs`), else the radio's own. */
const qruPath = (radio: PageRadio): string =>
  radio.id === PREFS_RADIO ? effectivePath(prefs.paths.value, pathOf(radio), "QRU").text : pathOf(radio);
/** The path INFO uses when none is typed: the one the radios share; null while they differ. */
const usual = computed(() => sharedPath(on.value, qruPath));
const typed = ref<string | null>(null); // typed text; null until typed (the field is then the map's radius)
const km = computed({
  get: () => typed.value ?? config.value?.values["map/radius_km"] ?? "",
  set: (text: string) => (typed.value = text),
});
const wrong = computed(() => kmWrong(km.value));
const servers = computed(() => qru.value?.servers ?? []);
/** The radio a server answered on while it is on and can send: where a request to it goes; null:
 * the ticked radios. */
const radioOf = (server: QruServer): PageRadio | null =>
  senders.value.find((radio) => radio.id === server.radio) ?? null;
/** The radios a request to a server goes on: the one it answered on, else those of Send on. */
const toServer = (server: QruServer): readonly PageRadio[] => {
  const one = radioOf(server);
  return one === null ? on.value : [one];
};
/** Each server with what its row says of the objects it sent, and its answering radio's tag
 * where radios are named. */
const rows = computed(() =>
  servers.value.map((server) => {
    const answered = server.radio === null || !named(server.radio) ? undefined : byId(server.radio);
    return { server, line: sentLine(server, now.value), answered };
  }),
);
const asked = computed(() => qru.value?.asked ?? null);
/** The seconds before the request may go on the radios: waits are per radio (the topic reports
 * the last request and its radios) and a request waits for every radio it would go on. */
const waitOn = (to: readonly PageRadio[], text: string | null): number => {
  const last = asked.value;
  const theirs =
    last !== null &&
    (last.radios.length === 0 || to.length === 0 || to.some((radio) => last.radios.includes(radio.id)));
  return askWait(theirs ? last : null, now.value, text);
};
const refusal = ref("");
const look = computed(() => {
  const found = qruLook(asked.value, servers.value, refusal.value, now.value);
  const name = refusal.value !== "" ? "" : radiosNamed(asked.value?.radios ?? [], byId, named);
  return found === null || name === "" ? found : { ...found, state: t("radio.line", { name, line: found.state }) };
});
/** Why a request on the radios that waits `seconds` may not go (RX only, radios, path, wait);
 * undefined when it may; "" while it goes on no radio that is on. */
const heldBy = (to: readonly PageRadio[], seconds: number): string | undefined => {
  const problem = routable(to) ? request.problem.value : "";
  return receiveOnly.value
    ? t("error.transmit.off")
    : several.value && to.length === 0
      ? ""
      : (radiosBlockedReason(to, named, told.value) ??
        (problem !== "" ? problem : seconds > 0 ? t("objects.qru_wait", { seconds }) : undefined));
};
const why = computed(() => heldBy(on.value, waitOn(on.value, requestText("INFO", km.value))));
/** Why a group's button is off (RX only, the server's radio, the path or its own wait);
 * undefined when it may be pressed. */
const groupWhy = (server: QruServer, word: string): string | undefined =>
  heldBy(toServer(server), waitOn(toServer(server), requestText(word, km.value)));

/** A request in flight: no button sends another until the daemon reports or refuses it. */
const asking = useCommandInFlight("qru_ask", () => asked.value?.at);

watch(lastError, (toast) => {
  if (toast?.cmd === "qru_ask") refusal.value = errorReason(toast, radios);
});
watch(
  () => asked.value?.at,
  () => (refusal.value = ""),
);

/** The request as the command carries it: the text, the path and RF only only when the fold
 * differs from the usual (an empty path and RF only ticked), and the single radio of a request
 * to a server while several are on (none: Send on's radios). */
function command(text: string, to: readonly PageRadio[], one: PageRadio | null): Command {
  const radio = several.value && one !== null ? { radio: one.id } : {};
  return !routable(to) || (request.sent.value === null && request.rfOnly.value)
    ? { cmd: "qru_ask", text, ...radio }
    : { cmd: "qru_ask", text, path: request.sent.value, rf_only: request.rfOnly.value, ...radio };
}

/** Send the INFO request with the field's distance on Send on's radios, unless held (RX only,
 * radios, path, wait). */
function ask(): void {
  const text = requestText("INFO", km.value);
  if (text === null || why.value !== undefined) return;
  refusal.value = "";
  asking.run(() => send(command(text, on.value, null)));
}

/** Send the request for a server's group with the field's distance on the radio the server
 * answered on, unless held. A group may go ten seconds after INFO, whose minute is not its own. */
function askGroup(server: QruServer, word: string): void {
  const text = requestText(word, km.value);
  if (text === null || groupWhy(server, word) !== undefined) return;
  refusal.value = "";
  asking.run(() => send(command(text, toServer(server), radioOf(server))));
}

/** Why Ask again is off (RX only, the server's radio, the path or that request's wait);
 * undefined when it may be pressed. */
const againWhy = (server: QruServer, text: string): string | undefined =>
  heldBy(toServer(server), waitOn(toServer(server), text));

/** The same request again as it went (its own distance), on the radio the server answered on. */
function again(server: QruServer, text: string): void {
  if (againWhy(server, text) !== undefined) return;
  refusal.value = "";
  asking.run(() => send(command(text, toServer(server), radioOf(server))));
}

/** The Stations tab, with the row of the first arrived object flashed. */
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
      <button
        type="button"
        class="btn"
        :disabled="why !== undefined || wrong || asking.busy.value"
        :title="why || undefined"
        @click="ask"
      >
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
      <InfoTip :label="t('settings.about', { label: t('objects.qru_km_label') })">{{
        t("objects.qru_km_tip")
      }}</InfoTip>
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
          ><TagMark v-if="answered" :tone="radioTone(answered)" :title="t('radio.heard_on', { name: answered.name })">{{
            answered.name
          }}</TagMark></span
        >
        <span class="qru-groups">
          <button
            v-for="group in server.groups"
            :key="group.name"
            type="button"
            class="btn small qru-group"
            :disabled="groupWhy(server, group.name) !== undefined || wrong || asking.busy.value"
            :title="
              groupWhy(server, group.name) ||
              t('objects.qru_group', { server: server.call, group: groupName(group.name) })
            "
            @click="askGroup(server, group.name)"
          >
            {{ categoryLabel(group.name) }}{{ " " }}<span class="qru-count">{{ group.count }}</span>
          </button>
        </span>
        <span
          v-if="line"
          class="qru-sent"
          :class="line.warn ? 'warn' : 'muted'"
          :title="line.warn ? t('objects.qru_lost_title') : server.sent"
        >
          {{ line.text }}
          <button
            v-if="line.again"
            type="button"
            class="btn small qru-again"
            :disabled="againWhy(server, line.again) !== undefined || asking.busy.value"
            :title="
              againWhy(server, line.again) || t('objects.qru_again_title', { server: server.call, request: line.again })
            "
            @click="again(server, line.again)"
          >
            {{ t("objects.qru_again") }}
          </button>
          <button
            v-if="server.received.length > 0"
            type="button"
            class="linkbutton qru-stations"
            @click="inStations(server.received)"
          >
            {{ t("objects.qru_in_stations", { tab: t("tab.stations") }) }}
          </button>
        </span>
      </li>
    </ul>
  </fieldset>
</template>
