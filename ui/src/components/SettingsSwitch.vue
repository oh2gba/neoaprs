<script setup lang="ts">
// A tickbox row of the Radio group (RX only, and Enable of the FM radio's box and of the HF radio's), worked as the form works a choice: it applies at once (`form.choose`). RX only is the setting the other way round (lib/settings.ts `valueFor`, `storedFor`).
// `only` greys the tickbox of the station's only radio (dimmed, its value kept, the (i) still opens) with a hover title that says why: a station has at least one radio, so there is no refusal to show.
import { computed } from "vue";
import SettingsField from "@/components/SettingsField.vue";
import type { Settings } from "@/composables/useSettings";
import { fieldId, type SettingsFormState } from "@/composables/useSettingsForm";
import { t } from "@/i18n";
import { FIELDS, storedFor, valueFor, type FieldInfo } from "@/lib/settings";

const props = defineProps<{ name: string; settings: Settings; form: SettingsFormState; defaults: Record<string, string>; only?: boolean }>();
const info = computed<FieldInfo>(() => {
  const own = FIELDS[props.name] ?? { label: props.name };
  return props.only ? { ...own, title: t("settings.enable.only_radio_title") } : own;
});
</script>

<template>
  <SettingsField
    :id="fieldId(name)"
    :info="info"
    :model-value="valueFor(name, settings.draft)"
    :fallback="defaults[name] ?? ''"
    :error="settings.errors[name] ?? ''"
    :changed="form.changed(name)"
    :apply="true"
    :disabled="only"
    @choose="form.choose({ [props.name]: storedFor(props.name, settings.draft, $event) })"
  />
</template>
