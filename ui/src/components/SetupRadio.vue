<script setup lang="ts">
// Step 4 of the first-run guide: the TNC profile, then for a serial TNC the port, picked from the list the daemon gives (`list_ports`, asked again by Refresh; "Automatic", the empty port, where the daemon looks for the radio itself) and the speed
// (the profile's own is the placeholder), or for KISS over TCP the host and the port.
import { computed } from "vue";
import SettingsField from "@/components/SettingsField.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { FIELDS, speedFallback, type FieldInfo } from "@/lib/settings";
import { portChoices } from "@/lib/setup";

const { guide, config } = useDaemonContext();
const defaults = computed<Record<string, string>>(() => config.value?.defaults ?? {});
const fields = computed(() => guide.fields);
const portInfo = computed(() => ({ label: "Port", kind: "choice" as const, choices: portChoices(guide.ports) }));
const fallback = (key: string): string => defaults.value[key] ?? "";
const info = (key: string): FieldInfo => FIELDS[key] ?? { label: key };
const err = (field: keyof typeof fields.value): string => guide.problems[field] ?? "";
</script>

<template>
  <SettingsField
    id="setup-profile"
    :info="info('tnc/profile')"
    :model-value="fields.profile"
    fallback=""
    :error="err('profile')"
    :changed="false"
    @update:model-value="guide.edit('profile', $event)"
  />
  <template v-if="guide.tcp">
    <SettingsField
      id="setup-host"
      :info="info('tcp/host')"
      :model-value="fields.host"
      :fallback="fallback('tcp/host')"
      :error="err('host')"
      :changed="false"
      @update:model-value="guide.edit('host', $event)"
    />
    <SettingsField
      id="setup-tcpport"
      :info="info('tcp/port')"
      :model-value="fields.tcpPort"
      :fallback="fallback('tcp/port')"
      :error="err('tcpPort')"
      :changed="false"
      @update:model-value="guide.edit('tcpPort', $event)"
    />
  </template>
  <template v-else>
    <SettingsField
      id="setup-port"
      :info="portInfo"
      :model-value="fields.port"
      fallback=""
      :error="err('port')"
      :changed="false"
      @update:model-value="guide.edit('port', $event)"
    >
      <template #after>
        <button type="button" class="btn" @click="guide.refreshPorts()">Refresh</button>
      </template>
    </SettingsField>
    <SettingsField
      id="setup-baud"
      :info="info('serial/baud')"
      :model-value="fields.baud"
      :fallback="speedFallback(fields.profile, fallback('serial/baud'))"
      :error="err('baud')"
      :changed="false"
      @update:model-value="guide.edit('baud', $event)"
    />
  </template>
</template>
