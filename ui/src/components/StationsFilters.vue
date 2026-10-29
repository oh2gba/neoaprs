<script setup lang="ts">
// The group box over the Stations table that narrows it: the filter box (Esc clears its text; with the box empty Esc is not taken, and goes on to close the newest card), the tickboxes "hide timed out", "direct only" and
// "heard on RF only" (it leaves out the stations known from the internet alone, and is there only once a station has been received over the internet: until then there is nothing for it to leave out), and "On map for" [3 h], how
// long a station stays on the map: the setting of the daemon (the same in every browser), changed at once with an Undo. The text and the tickboxes are the table's (StationsTable), which lists its rows by them.
import { computed } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import { STATION_HOURS_KEY, stationHours } from "@/lib/aging";
import { anyInternet } from "@/lib/channels";
import { FIELDS } from "@/lib/settings";

const filter = defineModel<string>("filter", { required: true });
const hideTimedOut = defineModel<boolean>("hideTimedOut", { required: true });
const directOnly = defineModel<boolean>("directOnly", { required: true });
const rfOnly = defineModel<boolean>("rfOnly", { required: true });
const { stations, settings } = useDaemonContext();

const internetKnown = computed(() => anyInternet(stations.value.values()));
const hours = computed(() =>
  String(stationHours({ [STATION_HOURS_KEY]: settings.draft[STATION_HOURS_KEY] ?? settings.values.value[STATION_HOURS_KEY] ?? "" })),
);
const hourChoices = computed(() => (FIELDS[STATION_HOURS_KEY]?.choices ?? []).map((c) => (typeof c === "string" ? { value: c, label: c } : c)));
function chooseHours(event: Event): void {
  settings.change({ [STATION_HOURS_KEY]: (event.target as HTMLSelectElement).value });
}

function clearFilter(event: KeyboardEvent): void {
  if (filter.value === "") return;
  filter.value = "";
  event.preventDefault();
}
</script>

<template>
  <fieldset class="filters">
    <legend>{{ t("station.table.filter") }}</legend>
    <div class="toolbar">
      <input
        v-model="filter"
        class="input filterbox"
        type="search"
        :placeholder="t('station.table.filter_title')"
        :title="t('station.table.filter_title')"
        :aria-label="t('station.table.filter_label')"
        @keydown.esc="clearFilter"
      />
      <div class="toolbar-checks">
        <label class="check"><input v-model="hideTimedOut" type="checkbox" /> {{ t("station.table.hide_timed_out") }}</label>
        <label class="check"><input v-model="directOnly" type="checkbox" /> {{ t("station.table.direct_only") }}</label>
        <label v-if="internetKnown" class="check" :title="t('station.table.rf_only_title')"
          ><input v-model="rfOnly" type="checkbox" /> {{ t("station.table.rf_only") }}</label
        >
        <label class="check onmap"
          >{{ t("station.table.on_map") }}
          <select id="stations-on-map" class="input" :value="hours" @change="chooseHours">
            <option v-for="choice in hourChoices" :key="choice.value" :value="choice.value">{{ choice.label }}</option>
          </select></label
        >
      </div>
    </div>
  </fieldset>
</template>
