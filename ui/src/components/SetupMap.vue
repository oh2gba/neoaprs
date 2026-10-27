<script setup lang="ts">
// Step 5 of the first-run guide: the map, which asks nothing. The daemon began downloading the detailed map round the station (the streets and names `map/radius_km` in every direction: 150 km unless the operator changed it) when the guide went on from the Position step;
// this step says so and shows how the download goes (MapFetchNotes: the bar, a failure, "Map downloaded"); the download goes on in the background after Finish, and the header of the page shows it too (the Map mark). Under it, for a station that will beacon, how often.
import InfoTip from "@/components/InfoTip.vue";
import MapFetchNotes from "@/components/MapFetchNotes.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { computed } from "vue";

const { guide, config, map } = useDaemonContext();
/** The beacon the station will have (or has after the save): the minutes, "" for none. */
const minutes = computed(() => Number(guide.changes["beacon/interval_min"] ?? config.value?.values["beacon/interval_min"] ?? ""));
/** The radius of the map the daemon makes: the setting, as the map topic tells it (else as the settings do). */
const radius = computed(() => map.value?.radius_km ?? Number(config.value?.values["map/radius_km"] ?? config.value?.defaults["map/radius_km"] ?? ""));
</script>

<template>
  <p class="setup-map">{{ t("setup.map_text", { radius }) }}</p>
  <MapFetchNotes v-if="map" :map="map" />
  <p v-if="minutes > 0" class="setup-beacon muted">
    {{ t("setup.beacon_every", { minutes }) }}
    <InfoTip :label="t('setup.beacon_tip_label')" picture="beacon">
      <span class="info-line">{{ t("setup.beacon_tip1") }}</span>
      <span class="info-line">{{ t("setup.beacon_tip2") }}</span>
    </InfoTip>
  </p>
</template>
