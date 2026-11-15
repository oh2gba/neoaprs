<script setup lang="ts">
// The main radio, the second row of the Radio group under RX only, there while the station has several radios: the radio that carries what goes to no station (bulletins, the status, the first choice of Ask around,
// Local info and email). Its choices are the radios that are on, by name; it shows the main radio in force (the daemon's `status.main_radio`) while the setting names none or a radio that is off. A choice applies at
// once, as any setting (`station/main_radio`, the radio's id); the daemon's refusal stands under it. While one radio is on (`off`) it is greyed, showing that radio: the row stays, so that ticking a second radio moves
// nothing under the pointer.
import { computed } from "vue";
import SettingsField from "@/components/SettingsField.vue";
import { useRadios } from "@/composables/useRadios";
import type { Settings } from "@/composables/useSettings";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { t } from "@/i18n";
import type { FieldInfo } from "@/lib/settings";
import { inputId } from "@/lib/settingsradio";

const KEY = "station/main_radio";
const props = defineProps<{ settings: Settings; form: SettingsFormState; off?: boolean }>();
const radios = useRadios();
const info = computed<FieldInfo>(() => ({
  label: t("radio.main"),
  tipLabel: t("radio.main.tip_label"),
  tip: [t("radio.main.tip1")],
  kind: "choice",
  choices: radios.enabled.value.map((radio) => ({ value: String(radio.id), label: radio.name })),
}));
/** The radio shown: the one the setting names while it is on, else the main radio in force. */
const shown = computed(() => {
  const named = props.settings.draft[KEY] ?? "";
  if (radios.enabled.value.some((radio) => String(radio.id) === named)) return named;
  return radios.main.value === null ? "" : String(radios.main.value.id);
});
</script>

<template>
  <SettingsField
    :id="inputId(KEY)"
    :info="info"
    :model-value="shown"
    fallback=""
    :error="settings.errors[KEY] ?? ''"
    :changed="form.changed(KEY)"
    :apply="true"
    :disabled="off"
    @choose="form.choose({ [KEY]: $event })"
  />
</template>
