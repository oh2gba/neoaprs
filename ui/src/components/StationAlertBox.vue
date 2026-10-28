<script setup lang="ts">
// "Alert me when…" for one station (from the menu of a row of the Stations table): a small box where the menu was, with the three things the daemon can watch, any of them at once (it comes on the air after half an hour of silence;
// it comes within so many km of us, 10 to start with, which needs our position; it is heard direct after half an hour without), and Save and Cancel. It shows the alert the station has, takes the focus on its first tickbox and keeps
// inside the window. Esc and Cancel close it with the focus back on `trigger` (the row or its "..." button), Save does too after it has sent the whole alert (all off takes it away), and a press outside it closes it. The daemon keeps
// the alert and fires it, with no page open too (lib/stationalert.ts).
import { computed, nextTick, onMounted, ref } from "vue";
import { usePopup } from "@/composables/usePopup";
import { t } from "@/i18n";
import { ALERT_KM_DEFAULT, ALERT_KM_MAX, ALERT_KM_MIN } from "@/lib/stationalert";
import type { AlertWhen } from "@/protocol/protocol";

const MARGIN = 8;

const props = defineProps<{ call: string; alert: AlertWhen | null; x: number; y: number; trigger: HTMLElement | null; placed: boolean }>();
const emit = defineEmits<{ save: [call: string, alert: AlertWhen]; close: [] }>();

const onAir = ref(props.alert?.on_air ?? false);
const near = ref(props.alert?.within_km != null);
const km = ref<number | string>(props.alert?.within_km ?? ALERT_KM_DEFAULT);
const direct = ref(props.alert?.direct ?? false);
/** The distance is a whole number of km in the daemon's range; it matters only while "comes within" is ticked. */
const kmOk = computed(() => typeof km.value === "number" && Number.isInteger(km.value) && km.value >= ALERT_KM_MIN && km.value <= ALERT_KM_MAX);

const root = ref<HTMLElement | null>(null);
const first = ref<HTMLInputElement | null>(null);
const open = ref(false);
const at = ref({ left: props.x, top: props.y });

function close(): void {
  open.value = false;
  emit("close");
}
/** Closed with the focus back where the menu was opened from. */
function finish(): void {
  close();
  props.trigger?.focus();
}
const popup = usePopup({ open, root, trigger: computed(() => props.trigger), close, focusAway: false, stopEscape: true });

onMounted(async () => {
  open.value = true;
  await nextTick();
  const box = root.value?.getBoundingClientRect();
  if (box) {
    at.value = {
      left: Math.max(MARGIN, Math.min(props.x, window.innerWidth - box.width - MARGIN)),
      top: Math.max(MARGIN, Math.min(props.y, window.innerHeight - box.height - MARGIN)),
    };
  }
  first.value?.focus();
});

function save(): void {
  if (near.value && !kmOk.value) return;
  emit("save", props.call, { on_air: onAir.value, within_km: near.value && typeof km.value === "number" ? km.value : null, direct: direct.value });
  finish();
}
</script>

<template>
  <div
    ref="root"
    class="alertbox"
    role="dialog"
    :aria-label="t('station.alert.label', { call })"
    :style="{ left: `${at.left}px`, top: `${at.top}px` }"
    @keydown="popup.onEscape"
    @contextmenu.prevent
  >
    <form @submit.prevent="save">
      <fieldset class="alertbox-group">
        <legend>{{ t("station.alert.label", { call }) }}</legend>
        <label class="check" :title="t('station.alert.on_air_title')"
          ><input ref="first" v-model="onAir" type="checkbox" data-alert="on_air" /> {{ t("station.alert.on_air") }}</label
        >
        <span class="alertbox-near">
          <label class="check"><input v-model="near" type="checkbox" data-alert="within" /> {{ t("station.alert.within") }}</label>
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
          />
          {{ t("station.alert.km") }}
        </span>
        <span class="alertbox-note muted">{{
          placed ? t("station.alert.km_range", { min: ALERT_KM_MIN, max: ALERT_KM_MAX }) : t("station.alert.no_position")
        }}</span>
        <label class="check" :title="t('station.alert.direct_title')"
          ><input v-model="direct" type="checkbox" data-alert="direct" /> {{ t("station.alert.direct") }}</label
        >
        <span class="alertbox-buttons">
          <button type="submit" class="btn primary" :disabled="near && !kmOk">{{ t("station.alert.save") }}</button>
          <button type="button" class="btn" @click="finish">{{ t("station.alert.cancel") }}</button>
        </span>
      </fieldset>
    </form>
  </div>
</template>
