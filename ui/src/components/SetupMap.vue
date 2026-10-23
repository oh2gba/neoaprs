<script setup lang="ts">
// Step 5 of the first-run guide: the radius of the base map and the button that downloads it (MapFetchPanel; the guide saves the answers first when they differ from the settings). Finish without
// downloading leaves the map for later.
import InfoTip from "@/components/InfoTip.vue";
import MapFetchPanel from "@/components/MapFetchPanel.vue";
import SettingsField from "@/components/SettingsField.vue";
import type { SetupGuide } from "@/composables/useSetupGuide";
import { FIELDS, type FieldInfo } from "@/lib/settings";
import type { MapState } from "@/protocol/protocol";
import { computed } from "vue";

const info = (key: string): FieldInfo => FIELDS[key] ?? { label: key };
const props = defineProps<{ guide: SetupGuide; defaults: Record<string, string>; map: MapState | null; beacon: string }>();
const minutes = computed(() => Number(props.beacon));
</script>

<template>
  <SettingsField
    id="setup-radius"
    :info="info('map/radius_km')"
    :model-value="props.guide.fields.radius"
    :fallback="props.defaults['map/radius_km'] ?? ''"
    :error="props.guide.problems.radius ?? ''"
    :changed="false"
    @update:model-value="props.guide.edit('radius', $event)"
  />
  <MapFetchPanel
    v-if="props.map"
    :map="props.map"
    :stale="props.guide.saving || !props.guide.valid[3] || !props.guide.valid[4]"
    early
    :send="props.guide.sendMap"
  />
  <p v-if="minutes > 0" class="setup-beacon muted">
    Beacon every {{ minutes }} min
    <InfoTip label="About the beacon">
      <span class="info-line">NeoAPRS sends your position at this interval, so that other stations see you on their map.</span>
      <span class="info-line">Change it, or switch it off, on the Beacon tab.</span>
    </InfoTip>
  </p>
</template>
