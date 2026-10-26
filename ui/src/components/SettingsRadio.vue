<script setup lang="ts">
// The TNC group of the Settings tab: the radio's status line with Reconnect in view, and behind its arrow the fields of the radio (the type of TNC, the port, the speed, or the host and port of a TNC reached over TCP), the Find my radio button
// and the terminal (RadioStatus). The fold is open when the radio is not connected. The fields are worked as in the form: a typed one is sent when it is left or Enter is pressed, a choice at once (the form's `settings` and `form`). Find my radio
// (FindRadioRow.vue) asks the daemon to try the ports and puts what it finds in the settings (composables/useFindRadio.ts).
import { computed } from "vue";
import FindRadioRow from "@/components/FindRadioRow.vue";
import RadioStatus from "@/components/RadioStatus.vue";
import SettingsField from "@/components/SettingsField.vue";
import SettingsPort from "@/components/SettingsPort.vue";
import type { Settings } from "@/composables/useSettings";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { fieldId, type SettingsFormState } from "@/composables/useSettingsForm";
import { FIELDS } from "@/lib/settings";
import { speedFallback } from "@/lib/tncprofile";

const props = defineProps<{ keys: readonly string[]; settings: Settings; form: SettingsFormState; defaults: Record<string, string> }>();
const { config, send, ports, tnc, now } = useDaemonContext();

const info = (key: string) => FIELDS[key] ?? { label: key };
const profile = computed(() => props.settings.draft["tnc/profile"]);
const digipeater = computed(() => config.value?.values["digi/enabled"] === "true");
/** The fold is open while the radio is not connected: that is when the fields are wanted. */
const unconnected = computed(() => tnc.value !== null && tnc.value.state !== "connected");
const fallback = (key: string) => (key === "serial/baud" ? speedFallback(profile.value, props.defaults[key] ?? "") : (props.defaults[key] ?? ""));
/** A typed field follows the typing; a choice is made by `choose` (it also says the text it has, which is not typing). */
function typed(key: string, text: string): void {
  const kind = info(key).kind;
  if (kind !== "bool" && kind !== "choice") props.settings.edit(key, text);
}
</script>

<template>
  <RadioStatus :tnc="tnc" :now="now" :digipeater="digipeater" :open="unconnected" @reconnect="send({ cmd: 'tnc_reconnect' })">
    <template v-for="key in keys" :key="key">
      <SettingsPort
        v-if="key === 'serial/port'"
        :id="fieldId(key)"
        :info="info(key)"
        :model-value="settings.draft[key] ?? ''"
        :found="config?.values['serial/last_port'] ?? ''"
        :ports="ports"
        :error="settings.errors[key] ?? ''"
        :changed="form.changed(key)"
        @update:model-value="settings.edit(key, $event)"
        @choose="form.choose({ [key]: $event })"
        @commit="form.finish(key, $event)"
        @cancel="settings.cancel(key)"
        @refresh="send({ cmd: 'list_ports' })"
      />
      <SettingsField
        v-else
        :id="fieldId(key)"
        :info="info(key)"
        :model-value="settings.draft[key] ?? ''"
        :fallback="fallback(key)"
        :error="settings.errors[key] ?? ''"
        :changed="form.changed(key)"
        :apply="true"
        @update:model-value="typed(key, $event)"
        @choose="form.choose({ [key]: $event })"
        @commit="form.finish(key, $event)"
        @cancel="settings.cancel(key)"
      />
    </template>
    <FindRadioRow id="find-radio" />
  </RadioStatus>
</template>
