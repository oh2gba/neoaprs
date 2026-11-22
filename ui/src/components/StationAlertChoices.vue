<script setup lang="ts">
// The "Alert me when…" choices for one station: three things the daemon can watch, any at once
// (back on the air after half an hour of silence; within a distance of us, which needs our
// position; heard direct after half an hour without). A distance outside 1 to 1000 km gets the
// orange edge. The values belong to the parent (useAlertDraft), which sends each change (`change`).
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
      <label class="check" :title="placed ? undefined : t('station.alert.no_position')"
        ><input v-model="near" type="checkbox" data-alert="within" :disabled="!placed && !near" @change="emit('change')" />
        {{ t("station.alert.within") }}</label
      >
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
    <label class="check" :title="t('station.alert.direct_title')"
      ><input v-model="direct" type="checkbox" data-alert="direct" @change="emit('change')" /> {{ t("station.alert.direct") }}</label
    >
  </fieldset>
</template>
