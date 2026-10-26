<script setup lang="ts">
// Step 5 of the first-run guide: the radius of the base map with the button that downloads it at the right end of the row (MapFetchButton, plain: the guide's one main action is Finish; the notes are under the row, MapFetchNotes; the guide saves the answers first when they differ from the settings). Finish without
// downloading leaves the map for later.
import InfoTip from "@/components/InfoTip.vue";
import MapFetchButton from "@/components/MapFetchButton.vue";
import MapFetchNotes from "@/components/MapFetchNotes.vue";
import SettingsField from "@/components/SettingsField.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { FIELDS, type FieldInfo } from "@/lib/settings";
import { computed } from "vue";

const info = (key: string): FieldInfo => FIELDS[key] ?? { label: key };
const { guide, config, map } = useDaemonContext();
/** The beacon the station will have (or has after the save): the minutes, "" for none. */
const minutes = computed(() => Number(guide.changes["beacon/interval_min"] ?? config.value?.values["beacon/interval_min"] ?? ""));
</script>

<template>
  <SettingsField
    id="setup-radius"
    :info="info('map/radius_km')"
    :model-value="guide.fields.radius"
    :fallback="(config?.defaults ?? {})['map/radius_km'] ?? ''"
    :error="guide.problems.radius ?? ''"
    :changed="false"
    @update:model-value="guide.edit('radius', $event)"
  >
    <template v-if="map" #after>
      <MapFetchButton :map="map" :stale="guide.saving || !guide.valid[3] || !guide.valid[4]" early :send="guide.sendMap" />
    </template>
  </SettingsField>
  <MapFetchNotes v-if="map" :map="map" />
  <p v-if="minutes > 0" class="setup-beacon muted">
    {{ t("setup.beacon_every", { minutes }) }}
    <InfoTip :label="t('setup.beacon_tip_label')" picture="beacon">
      <span class="info-line">{{ t("setup.beacon_tip1") }}</span>
      <span class="info-line">{{ t("setup.beacon_tip2") }}</span>
    </InfoTip>
  </p>
</template>
