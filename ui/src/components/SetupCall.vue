<script setup lang="ts">
// Step 1 of the first-run guide: the call, checked as it is typed (the rules of lib/calls.ts; N0CALL is refused).
import SettingsField from "@/components/SettingsField.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";

const { guide } = useDaemonContext();
/** The field's own words, made when the page is drawn so that they follow the language. */
const info = () => ({ label: t("setup.call.label"), empty: "OH2ABC-9" });
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
