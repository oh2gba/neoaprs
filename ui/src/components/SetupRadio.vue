<script setup lang="ts">
// Step 4 of the first-run guide: the TNC profile, then for a serial TNC the port, picked from the list the daemon gives (`list_ports`, asked again by Refresh; "Automatic", the empty port, where the daemon looks for the radio itself) and the speed
// (the profile's own is the placeholder), or for KISS over TCP the host and the port, or for the Dummy radio nothing: no port, no speed. Under the fields are Find my radio (a serial TNC; it fills the type, the port and the speed) and
// the Terminal, the same two as in the Settings tab: opening the terminal puts the radio the answers name in force, so that it shows that radio.
import { computed } from "vue";
import FindRadioRow from "@/components/FindRadioRow.vue";
import SettingsField from "@/components/SettingsField.vue";
import TncTerminal from "@/components/TncTerminal.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { FIELDS, type FieldInfo } from "@/lib/settings";
import { speedFallback } from "@/lib/tncprofile";
import { isDummy, portChoices } from "@/lib/setup";

const { guide, config, tnc } = useDaemonContext();
const defaults = computed<Record<string, string>>(() => config.value?.defaults ?? {});
const fields = computed(() => guide.fields);
const dummy = computed(() => isDummy(guide.fields));
const portInfo = computed(() => ({ label: t("settings.port.label"), kind: "choice" as const, choices: portChoices(guide.ports) }));
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
  <template v-else-if="!dummy">
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
        <button type="button" class="btn" @click="guide.refreshPorts()">{{ t("settings.port.refresh") }}</button>
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
    <FindRadioRow id="setup-find-radio" />
  </template>
  <TncTerminal :tnc="tnc" @toggle="(open) => open && guide.applyRadio()" />
</template>
