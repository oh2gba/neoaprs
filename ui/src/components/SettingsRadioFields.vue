<script setup lang="ts">
// The fields of one radio of the Radio group, each worked as in the form: a typed one is sent when it is left or Enter is pressed, a choice at once (the form's `settings` and `form`). The FM radio's are the type of TNC, the port (SettingsPort, with the port the search found beside it), the speed, or the host and port of a TNC reached over TCP;
// the HF radio's are its type, the sound card, a plain choice among what the daemon found (the system's name for each, its id the hover title; Refresh beside it), and the keying, a choice made of the ports the daemon lists (lib/mercury.ts), and beside the
// keying the Test button, which keys the radio for a second so that the operator sees it go to transmit and come back (composables/useHfTests.ts); the status line says Keyed meanwhile.
// Neither offers "find automatically": the daemon's proposal (`pick` of a sound card, `keying` of the ports message) is preselected and stored as the setting while it is empty, the card first and the keying once that is answered, so that
// the settings name a card and a keying as soon as the HF radio is on. (An empty setting stays legal for the daemon, and a station that has one runs as before; the page never offers it.)
import { computed, watchEffect } from "vue";
import SettingsField from "@/components/SettingsField.vue";
import SettingsPort from "@/components/SettingsPort.vue";
import type { Settings } from "@/composables/useSettings";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useHfTests } from "@/composables/useHfTests";
import { fieldId, type SettingsFormState } from "@/composables/useSettingsForm";
import { t } from "@/i18n";
import { keyingChoices, soundCardChoices, soundCardPick } from "@/lib/mercury";
import { FIELDS, type FieldInfo } from "@/lib/settings";
import { speedFallback } from "@/lib/tncprofile";

const props = defineProps<{ keys: readonly string[]; settings: Settings; form: SettingsFormState; defaults: Record<string, string> }>();
const { config, send, ports } = useDaemonContext();

const SOUND_CARD_KEY = "mercury/sound_card";
const KEYING_KEY = "mercury/keying";
const info = (key: string) => FIELDS[key] ?? { label: key };
const fallback = (key: string) =>
  key === "serial/baud" ? speedFallback(props.settings.draft["tnc/profile"], props.defaults[key] ?? "") : (props.defaults[key] ?? "");
/** The daemon's proposals, which the field shows as chosen while the setting is empty and which the page then stores. */
const pick = (key: string): string => (key === SOUND_CARD_KEY ? soundCardPick(ports.value) : (ports.value?.keying ?? ""));
const valueOf = (key: string): string => (props.settings.draft[key] ?? "") || pick(key);
const cardInfo = computed<FieldInfo>(() => ({ ...info(SOUND_CARD_KEY), kind: "choice", choices: soundCardChoices(ports.value) }));
const keyingInfo = computed<FieldInfo>(() => ({ ...info(KEYING_KEY), kind: "choice", choices: keyingChoices(ports.value, valueOf(KEYING_KEY)) }));
const infoOf = (key: string): FieldInfo => (key === SOUND_CARD_KEY ? cardInfo.value : key === KEYING_KEY ? keyingInfo.value : info(key));
// An empty setting takes the proposal: the card first, the keying when nothing is out any more (the form sends one change at a time).
watchEffect(() => {
  for (const key of [SOUND_CARD_KEY, KEYING_KEY]) {
    const proposal = pick(key);
    if (!props.keys.includes(key) || proposal === "" || (props.settings.draft[key] ?? "") !== "" || props.settings.expected(key) !== "") continue;
    if (!props.settings.saving.value) props.form.choose({ [key]: proposal });
    break;
  }
});
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
    <SettingsField
      v-else
      :id="fieldId(key)"
      :info="infoOf(key)"
      :model-value="valueOf(key)"
      :fallback="fallback(key)"
      :error="settings.errors[key] ?? ''"
      :changed="form.changed(key)"
      :apply="true"
      @update:model-value="typed(key, $event)"
      @choose="form.choose({ [key]: $event })"
      @commit="form.finish(key, $event)"
      @cancel="settings.cancel(key)"
    >
      <template v-if="key === SOUND_CARD_KEY" #after>
        <button class="btn" type="button" @click="send({ cmd: 'list_ports' })">{{ t("settings.port.refresh") }}</button>
      </template>
      <template v-else-if="key === KEYING_KEY" #after>
        <button id="hf-key-test" class="btn" type="button" :disabled="tests.testOff.value" :title="tests.why.value" @click="tests.keyTest">
          {{ t("settings.keying.test") }}
        </button>
      </template>
    </SettingsField>
  </template>
</template>
