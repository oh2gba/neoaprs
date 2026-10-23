<script setup lang="ts">
// A closed heading in a group of the form (DisclosureBox) with some of its fields under it: the Beacon group's Antenna (power, height, gain and direction, which make the PHG part of the beacon) and Advanced (the path). The fields are
// worked as in the form: a typed one is sent when it is left or Enter is pressed, a choice at once (the form's `settings` and `form`).
import DisclosureBox from "@/components/DisclosureBox.vue";
import SettingsField from "@/components/SettingsField.vue";
import type { Settings } from "@/composables/useSettings";
import { fieldId, type SettingsFormState } from "@/composables/useSettingsForm";
import { FIELDS } from "@/lib/settings";

defineProps<{ title: string; keys: readonly string[]; settings: Settings; form: SettingsFormState; defaults: Record<string, string> }>();
</script>

<template>
  <DisclosureBox v-if="keys.length > 0" class="settings-fold" :title="title">
    <SettingsField
      v-for="key in keys"
      :id="fieldId(key)"
      :key="key"
      :info="FIELDS[key] ?? { label: key }"
      :model-value="settings.draft[key] ?? ''"
      :fallback="defaults[key] ?? ''"
      :error="settings.errors[key] ?? ''"
      :changed="form.changed(key)"
      :apply="true"
      @update:model-value="FIELDS[key]?.kind === 'choice' ? undefined : settings.edit(key, $event)"
      @choose="form.choose({ [key]: $event })"
      @commit="form.finish(key, $event)"
      @cancel="settings.cancel(key)"
    />
  </DisclosureBox>
</template>
