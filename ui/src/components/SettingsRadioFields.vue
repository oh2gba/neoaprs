<script setup lang="ts">
// The fields of one radio of the Radio group, each worked as in the form: a typed one is sent when it is left or Enter is pressed, a choice at once (the form's `settings` and `form`). The FM radio's are the type of TNC, the port (SettingsPort, with the port the search found beside it), the speed, or the host and port of a TNC reached over TCP;
// the HF radio's are its type, the sound card, a list of what the daemon found as the port is (SettingsPort), and the keying, a choice made of the ports the daemon lists (lib/mercury.ts), each with what the daemon runs the modem with beside it while it is left at find automatically, and beside the
// keying the Test button, which keys the radio for a second with next to no audio so that the operator sees it go to transmit and come back (composables/useHfTests.ts); the status line says Keyed meanwhile.
import { computed } from "vue";
import SettingsField from "@/components/SettingsField.vue";
import SettingsPort from "@/components/SettingsPort.vue";
import type { Settings } from "@/composables/useSettings";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useHfTests } from "@/composables/useHfTests";
import { fieldId, type SettingsFormState } from "@/composables/useSettingsForm";
import { t } from "@/i18n";
import { keyingChoices, keyingLabel, soundCardPorts } from "@/lib/mercury";
import { FIELDS, type FieldInfo } from "@/lib/settings";
import { speedFallback } from "@/lib/tncprofile";

const props = defineProps<{ keys: readonly string[]; settings: Settings; form: SettingsFormState; defaults: Record<string, string> }>();
const { config, send, ports, hf } = useDaemonContext();

const SOUND_CARD_KEY = "mercury/sound_card";
const KEYING_KEY = "mercury/keying";
const info = (key: string) => FIELDS[key] ?? { label: key };
const fallback = (key: string) =>
  key === "serial/baud" ? speedFallback(props.settings.draft["tnc/profile"], props.defaults[key] ?? "") : (props.defaults[key] ?? "");
const soundCards = computed(() => soundCardPorts(ports.value));
const keyingInfo = computed<FieldInfo>(() => ({
  ...info(KEYING_KEY),
  kind: "choice",
  choices: [{ value: "", label: t("settings.port.auto") }, ...keyingChoices(ports.value, props.settings.draft[KEYING_KEY] ?? "")],
}));
/** What the daemon runs the modem with while a setting is empty: its own choice, said beside the field as the port found is. */
const chosenCard = computed(() => hf.value?.modem?.sound_card ?? "");
const chosenKeying = computed(() => (hf.value?.modem ? keyingLabel(hf.value.modem.keying) : ""));
const tests = useHfTests();
/** A typed field follows the typing; a choice is made by `choose` (it also says the text it has, which is not typing). */
function typed(key: string, text: string): void {
  const kind = info(key).kind;
  if (kind !== "bool" && kind !== "choice") props.settings.edit(key, text);
}
</script>

<template>
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
    <SettingsPort
      v-else-if="key === SOUND_CARD_KEY"
      :id="fieldId(key)"
      :info="info(key)"
      :model-value="settings.draft[key] ?? ''"
      :found="chosenCard"
      :first="t('settings.port.auto')"
      :typed-label="t('settings.sound_card.id_label')"
      :ports="soundCards"
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
      :info="key === KEYING_KEY ? keyingInfo : info(key)"
      :model-value="settings.draft[key] ?? ''"
      :fallback="fallback(key)"
      :error="settings.errors[key] ?? ''"
      :changed="form.changed(key)"
      :apply="true"
      @update:model-value="typed(key, $event)"
      @choose="form.choose({ [key]: $event })"
      @commit="form.finish(key, $event)"
      @cancel="settings.cancel(key)"
    >
      <template v-if="key === KEYING_KEY" #after>
        <span v-if="(settings.draft[key] ?? '') === '' && chosenKeying !== ''" class="muted port-found">{{
          t("settings.port.found", { port: chosenKeying })
        }}</span>
        <button id="hf-key-test" class="btn" type="button" :disabled="tests.testOff.value" :title="tests.why.value" @click="tests.keyTest">
          {{ t("settings.keying.test") }}
        </button>
      </template>
    </SettingsField>
  </template>
</template>
