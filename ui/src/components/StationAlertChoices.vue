<script setup lang="ts">
// The choices of "Alert me when…" for one station, a group box with the legend "Alert me when OH2XYZ…": the three things the daemon can watch, any of them at once (it comes on the air after half an hour of silence; it comes
// within so many km of us, which needs our position: while there is none a quiet line under it says so; it is heard direct after half an hour without). A distance out of the daemon's range (1 to 1000 km) has the red edge of
// every field that is wrong, and no line says the range. The values are the parent's (composables/useAlertDraft.ts): the station panel of the Stations tab (StationPanel) sends them as each is changed (`change`: a tickbox ticked
// or cleared, the distance changed and left or Enter pressed).
import { t } from "@/i18n";
import { ALERT_KM_MAX, ALERT_KM_MIN } from "@/lib/stationalert";

defineProps<{ call: string; placed: boolean; kmOk: boolean }>();
const emit = defineEmits<{ change: [] }>();
const onAir = defineModel<boolean>("onAir", { required: true });
const near = defineModel<boolean>("near", { required: true });
const km = defineModel<number | string>("km", { required: true });
const direct = defineModel<boolean>("direct", { required: true });
</script>

<template>
  <fieldset class="alertbox-group">
    <legend>{{ t("station.alert.label", { call }) }}</legend>
    <label class="check" :title="t('station.alert.on_air_title')"
      ><input v-model="onAir" type="checkbox" data-alert="on_air" @change="emit('change')" /> {{ t("station.alert.on_air") }}</label
    >
    <span class="alertbox-near">
      <label class="check"><input v-model="near" type="checkbox" data-alert="within" @change="emit('change')" /> {{ t("station.alert.within") }}</label>
      <input
        v-model.number="km"
        class="input alertbox-km"
        type="number"
        inputmode="numeric"
        :min="ALERT_KM_MIN"
        :max="ALERT_KM_MAX"
        step="1"
        :disabled="!near"
        :class="{ invalid: near && !kmOk }"
        :aria-invalid="near && !kmOk"
        :aria-label="t('station.alert.km_label')"
        @change="emit('change')"
      />
      {{ t("station.alert.km") }}
    </span>
    <span v-if="!placed" class="alertbox-note muted">{{ t("station.alert.no_position") }}</span>
    <label class="check" :title="t('station.alert.direct_title')"
      ><input v-model="direct" type="checkbox" data-alert="direct" @change="emit('change')" /> {{ t("station.alert.direct") }}</label
    >
  </fieldset>
</template>
