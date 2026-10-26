<script setup lang="ts">
// Local info (QRU), the last group box of the Nearby tab: **Ask** sends INFO to the stations near us (one request by radio only: the daemon sends it once, with RFONLY, at most one in a minute, and refuses it in RX only) with a distance in km that starts at the
// map's radius (empty: the servers' own); under it the one status row of the groups (StatusFold): when the last request was sent and waiting for answers, then how many servers answered or that none did, or why it was refused. Ask is held for the minute,
// with the time left in its title. The servers that answered are a row each: its call, its groups as tags (the number of objects in each; a press asks that group, with the same distance) and under them, quiet, the line it closed its last objects with.
// The objects themselves arrive as ordinary objects (the map, the Stations tab).
import { computed, ref, watch } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import StatusFold from "@/components/StatusFold.vue";
import TagMark from "@/components/TagMark.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import { errorReason } from "@/i18n/errortext";
import { askWait, kmWrong, qruLook, requestText } from "@/lib/qru";
import { LIMITS } from "@/protocol/lists";

const { qru, receiveOnly, send, config, lastError, now } = useDaemonContext();
const typed = ref<string | null>(null); // (what the person typed; null until then, and the field is the map's radius)
const km = computed({
  get: () => typed.value ?? config.value?.values["map/radius_km"] ?? "",
  set: (text: string) => (typed.value = text),
});
const wrong = computed(() => kmWrong(km.value));
const servers = computed(() => qru.value?.servers ?? []);
const asked = computed(() => qru.value?.asked ?? null);
const wait = computed(() => askWait(asked.value, now.value));
const refusal = ref(""); // (why the daemon refused the last request, until the next one)
const look = computed(() => qruLook(asked.value, servers.value, refusal.value, now.value));
const off = computed(() => receiveOnly.value || wait.value > 0);
const why = computed(() => (receiveOnly.value ? t("pill.rx_send") : wait.value > 0 ? t("nearby.qru_wait", { seconds: wait.value }) : undefined));

watch(lastError, (toast) => {
  if (toast?.cmd === "qru_ask") refusal.value = errorReason(toast);
});
watch(
  () => asked.value?.at,
  () => (refusal.value = ""),
);

/** Sends the request for the word (INFO or a group) with the distance of the field. */
function ask(word: string): void {
  const text = requestText(word, km.value);
  if (off.value || text === null) return;
  refusal.value = "";
  send({ cmd: "qru_ask", text });
}
</script>

<template>
  <fieldset class="nearby-section nearby-qru">
    <legend class="nearby-head">
      {{ t("nearby.qru") }} <span v-if="servers.length > 0" class="muted">{{ servers.length }}</span>
      <InfoTip :label="t('nearby.qru_tip_label')" picture="qru">
        <span class="info-line">{{ t("nearby.qru_tip") }}</span>
        <span class="info-line">{{ t("nearby.qru_tip2") }}</span>
      </InfoTip>
    </legend>
    <div class="qru-ask">
      <button type="button" class="btn primary" :disabled="off || wrong" :title="why" @click="ask('INFO')">{{ t("nearby.qru_ask") }}</button>
      <input
        v-model="km"
        class="input mono qru-km"
        :class="{ invalid: wrong }"
        type="text"
        inputmode="numeric"
        autocomplete="off"
        :maxlength="String(LIMITS.qru.kmMax).length"
        :placeholder="t('nearby.qru_km')"
        :aria-label="t('nearby.qru_km_label')"
        @keydown.enter="ask('INFO')"
      />
      <InfoTip :label="t('settings.about', { label: t('nearby.qru_km_label') })">{{ t("nearby.qru_km_tip") }}</InfoTip>
    </div>
    <StatusFold v-if="look" class="qrustatus" :state="look.state" :tone="look.tone" :line="look.line">
      <template v-if="asked" #default>
        <p class="igatefold">{{ t("nearby.qru_request", { text: asked.text }) }}</p>
      </template>
    </StatusFold>
    <ul v-if="servers.length > 0" class="qru-servers" :aria-label="t('nearby.qru')">
      <li v-for="server in servers" :key="server.call" class="qru-server">
        <span class="mono strong qru-call">{{ server.call }}</span>
        <span class="qru-groups">
          <TagMark
            v-for="group in server.groups"
            :key="group.name"
            as="button"
            tone="accent"
            class="qru-group"
            :disabled="off || wrong"
            :title="why ?? t('nearby.qru_group', { server: server.call, group: group.name })"
            @click="ask(group.name)"
            >{{ group.name }}{{ " " }}<span class="qru-count">{{ group.count }}</span></TagMark
          >
        </span>
        <span v-if="server.sent !== ''" class="muted qru-sent">{{ server.sent }}</span>
      </li>
    </ul>
  </fieldset>
</template>
