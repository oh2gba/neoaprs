<script setup lang="ts">
// Step 1 of the first-run guide: the call, checked as it is typed (the rules of lib/calls.ts; N0CALL is refused).
import SettingsField from "@/components/SettingsField.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";

const { guide } = useDaemonContext();
const info = { label: "Your call", empty: "OH2ABC-9" };
</script>

<template>
  <SettingsField
    id="setup-call"
    :info="info"
    :model-value="guide.fields.call"
    fallback=""
    :error="guide.problems.call ?? ''"
    :changed="false"
    @update:model-value="guide.edit('call', $event)"
  />
</template>
