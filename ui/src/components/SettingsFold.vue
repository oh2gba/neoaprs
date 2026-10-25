<script setup lang="ts">
// A closed heading in a group of the form (DisclosureBox) with some of its fields under it: the Beacon group's Antenna (power, height, gain and direction, which make the PHG part of the beacon) and Advanced (the path, which is one choice: SettingsPath). The fields are
// worked as in the form (a field the form greys out, `disabled`, is shown with its value and cannot be changed; the fold still opens): a typed one is sent when it is left or Enter is pressed, a choice at once (the form's `settings` and `form`).
import DisclosureBox from "@/components/DisclosureBox.vue";
import SettingsField from "@/components/SettingsField.vue";
import SettingsPath from "@/components/SettingsPath.vue";
import type { Settings } from "@/composables/useSettings";
import { fieldId, type SettingsFormState } from "@/composables/useSettingsForm";
import { FIELDS } from "@/lib/settings";
import { recommendedPath } from "@/lib/symbols";

defineProps<{
  title: string;
  keys: readonly string[];
  settings: Settings;
  form: SettingsFormState;
  defaults: Record<string, string>;
  disabled?: (key: string) => boolean;
}>();
</script>

<template>
  <DisclosureBox v-if="keys.length > 0" class="settings-fold" :title="title">
    <template v-for="key in keys" :key="key">
      <SettingsPath
        v-if="key === 'beacon/path'"
        :id="fieldId(key)"
        :info="FIELDS[key] ?? { label: key }"
        :model-value="settings.draft[key] ?? ''"
        :error="settings.errors[key] ?? ''"
        :changed="form.changed(key)"
        :recommended="recommendedPath(settings.draft['station/symbol_table'] ?? '', settings.draft['station/symbol_code'] ?? '')"
        :disabled="disabled?.(key)"
        @update:model-value="settings.edit(key, $event)"
        @choose="form.choose({ [key]: $event })"
        @commit="form.finish(key, $event)"
        @cancel="settings.cancel(key)"
      />
      <SettingsField
        v-else
        :id="fieldId(key)"
        :info="FIELDS[key] ?? { label: key }"
        :model-value="settings.draft[key] ?? ''"
        :fallback="defaults[key] ?? ''"
        :error="settings.errors[key] ?? ''"
        :changed="form.changed(key)"
        :apply="true"
        :disabled="disabled?.(key)"
        @update:model-value="FIELDS[key]?.kind === 'choice' ? undefined : settings.edit(key, $event)"
        @choose="form.choose({ [key]: $event })"
        @commit="form.finish(key, $event)"
        @cancel="settings.cancel(key)"
      />
    </template>
  </DisclosureBox>
</template>
