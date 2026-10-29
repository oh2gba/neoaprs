<script setup lang="ts">
// The choices of "Alert me when…" for one station, a group box with the legend "Alert me when OH2XYZ…": the three things the daemon can watch, any of them at once (it comes on the air after half an hour of silence; it comes
// within so many km of us, which needs our position: the quiet line under it says the range, or that the position is missing; it is heard direct after half an hour without). The values are the parent's (composables/useAlertDraft.ts):
// the box of the menu (StationAlertBox) puts its Save and Cancel in the slot and sends them with Save; the field under a row of the Stations table (StationRowDetail) sends them as each is changed (`change`: a tickbox ticked
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
        :aria-invalid="near && !kmOk"
        :aria-label="t('station.alert.km_label')"
        @change="emit('change')"
      />
      {{ t("station.alert.km") }}
    </span>
    <span class="alertbox-note muted">{{
      placed ? t("station.alert.km_range", { min: ALERT_KM_MIN, max: ALERT_KM_MAX }) : t("station.alert.no_position")
    }}</span>
    <label class="check" :title="t('station.alert.direct_title')"
      ><input v-model="direct" type="checkbox" data-alert="direct" @change="emit('change')" /> {{ t("station.alert.direct") }}</label
    >
    <slot />
  </fieldset>
</template>
