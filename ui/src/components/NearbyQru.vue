<script setup lang="ts">
// Local info (QRU), the last section of the Nearby tab: **Ask** sends INFO to the stations near us (one request by radio only: the daemon sends it once, with RFONLY, and it is refused in RX only) with an optional distance in km (empty: the servers' own); the servers
// that answered are a row each: its call, its groups as pills (the number of objects in each; a press asks that group, with the same distance) and under them, quiet, the line it closed its last objects with. "No answer yet" stands once something was asked and nobody
// has answered. The objects themselves arrive as ordinary objects (the map, the Stations tab).
import { computed, ref } from "vue";
import InfoTip from "@/components/InfoTip.vue";
import TagMark from "@/components/TagMark.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import { kmWrong, requestText } from "@/lib/qru";
import { LIMITS } from "@/protocol/lists";

const { qru, receiveOnly, send } = useDaemonContext();
const km = ref("");
const wrong = computed(() => kmWrong(km.value));
const servers = computed(() => qru.value?.servers ?? []);
const waiting = computed(() => qru.value?.asked != null && servers.value.length === 0);
const why = computed(() => (receiveOnly.value ? t("pill.rx_send") : undefined));

/** Sends the request for the word (INFO or a group) with the distance of the field. */
function ask(word: string): void {
  const text = requestText(word, km.value);
  if (text !== null) send({ cmd: "qru_ask", text });
}
</script>

<template>
  <section class="nearby-section nearby-qru" aria-labelledby="nearby-qru">
    <div class="nearby-head">
      <h3 id="nearby-qru" class="board-title">
        {{ t("nearby.qru") }} <span v-if="servers.length > 0" class="muted">{{ servers.length }}</span>
      </h3>
      <InfoTip :label="t('nearby.qru_tip_label')" picture="qru">{{ t("nearby.qru_tip") }}</InfoTip>
    </div>
    <div class="qru-ask">
      <button type="button" class="btn primary" :disabled="receiveOnly || wrong" :title="why" @click="ask('INFO')">{{ t("nearby.qru_ask") }}</button>
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
        @keydown.enter="!receiveOnly && ask('INFO')"
      />
      <InfoTip :label="t('settings.about', { label: t('nearby.qru_km_label') })">{{ t("nearby.qru_km_tip") }}</InfoTip>
    </div>
    <p v-if="waiting" class="muted nearby-help qru-none">{{ t("nearby.qru_none") }}</p>
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
            :disabled="receiveOnly || wrong"
            :title="receiveOnly ? t('pill.rx_send') : t('nearby.qru_group', { server: server.call, group: group.name })"
            @click="ask(group.name)"
            >{{ group.name }}{{ " " }}<span class="qru-count">{{ group.count }}</span></TagMark
          >
        </span>
        <span v-if="server.sent !== ''" class="muted qru-sent">{{ server.sent }}</span>
      </li>
    </ul>
  </section>
</template>
