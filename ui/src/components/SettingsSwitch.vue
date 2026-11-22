<script setup lang="ts">
// A tickbox row of the Radio group (RX only, Enable), applied at once (`form.choose`). RX only is
// the setting inverted (lib/settings.ts `valueFor`, `storedFor`). `only` greys the tickbox of the
// only radio, with a hover title that says why.
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
