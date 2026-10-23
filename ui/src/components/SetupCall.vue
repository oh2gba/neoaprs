<script setup lang="ts">
// Step 1 of the first-run guide: the call, checked as it is typed (the rules of lib/calls.ts; N0CALL is refused).
import SettingsField from "@/components/SettingsField.vue";
import type { SetupGuide } from "@/composables/useSetupGuide";

const props = defineProps<{ guide: SetupGuide }>();
const info = { label: "Your call", empty: "OH2ABC-9" };
</script>

<template>
  <SettingsField
    id="setup-call"
    :info="info"
    :model-value="props.guide.fields.call"
    fallback=""
    :error="props.guide.problems.call ?? ''"
    :changed="false"
    @update:model-value="props.guide.edit('call', $event)"
  />
</template>
