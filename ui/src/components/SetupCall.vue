<script setup lang="ts">
// Step 1 of the first-run guide: the call and the SSID, checked as typed (lib/calls.ts; N0CALL is
// refused).
import SettingsField from "@/components/SettingsField.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";

const { guide } = useDaemonContext();
/** The field's words, made at draw time so that they follow the language. */
const info = () => ({
  label: t("setup.call.label"),
  empty: "OH2ABC",
  kind: "call" as const,
  tip: [t("settings.call.tip1"), t("settings.call.tip2")],
  picture: "ssid" as const,
});
</script>

<template>
  <SettingsField
    id="setup-call"
    :info="info()"
    :model-value="guide.fields.call"
    fallback=""
    :error="guide.problems.call ?? ''"
    :changed="false"
    @update:model-value="guide.edit('call', $event)"
  />
</template>
