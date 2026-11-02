<script setup lang="ts">
// The Radio group of the Settings tab: the RX only tickbox first (ticked is `station/transmit` false), then the radio's status line, and behind its arrow the fields of the radio (the type of TNC, the port, the speed, or the host and port of a TNC reached over TCP, or the sound card and the keying of the Mercury HF modem), the Find my radio button
// and the terminal (RadioStatus). The fold is open when the radio is not connected. The fields are worked as in the form: a typed one is sent when it is left or Enter is pressed, a choice at once (the form's `settings` and `form`). Find my radio
// (FindRadioRow.vue) asks the daemon to try the ports and puts what it finds in the settings (composables/useFindRadio.ts). The sound card is a list of what the daemon found, as the port is (SettingsPort), and the keying a choice made of the ports the
// daemon lists (lib/mercury.ts); both lists are asked for again when the type becomes Mercury, since the daemon lists the sound cards only then.
import { computed, watch } from "vue";
import FindRadioRow from "@/components/FindRadioRow.vue";
import RadioStatus from "@/components/RadioStatus.vue";
import SettingsField from "@/components/SettingsField.vue";
import SettingsPort from "@/components/SettingsPort.vue";
import type { Settings } from "@/composables/useSettings";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { fieldId, type SettingsFormState } from "@/composables/useSettingsForm";
import { t } from "@/i18n";
import { keyingChoices, keyingLabel, soundCardPorts } from "@/lib/mercury";
import { FIELDS, RX_ONLY_KEY, storedFor, valueFor, type FieldInfo } from "@/lib/settings";
import { profileOf, speedFallback } from "@/lib/tncprofile";

const props = defineProps<{ keys: readonly string[]; settings: Settings; form: SettingsFormState; defaults: Record<string, string> }>();
const { config, send, ports, tnc, now } = useDaemonContext();

/** The switch that is the first row of the group, above the status line: transmitting at all. */
const TRANSMIT_KEY = RX_ONLY_KEY;
const SOUND_CARD_KEY = "mercury/sound_card";
const KEYING_KEY = "mercury/keying";
const info = (key: string) => FIELDS[key] ?? { label: key };
const profile = computed(() => props.settings.draft["tnc/profile"]);
const modem = computed(() => profileOf(profile.value)?.transport === "modem");
/** The fold is open while the radio is not connected: that is when the fields are wanted. */
const unconnected = computed(() => tnc.value !== null && tnc.value.state !== "connected");
const fallback = (key: string) => (key === "serial/baud" ? speedFallback(profile.value, props.defaults[key] ?? "") : (props.defaults[key] ?? ""));
const soundCards = computed(() => soundCardPorts(ports.value));
const keyingInfo = computed<FieldInfo>(() => ({
  ...info(KEYING_KEY),
  kind: "choice",
  choices: [{ value: "", label: t("settings.port.auto") }, ...keyingChoices(ports.value, props.settings.draft[KEYING_KEY] ?? "")],
}));
/** What the daemon runs the modem with while a setting is empty: its own choice, said beside the field as the port found is. */
const chosenCard = computed(() => tnc.value?.modem?.sound_card ?? "");
const chosenKeying = computed(() => (tnc.value?.modem ? keyingLabel(tnc.value.modem.keying) : ""));
/** A typed field follows the typing; a choice is made by `choose` (it also says the text it has, which is not typing). */
function typed(key: string, text: string): void {
  const kind = info(key).kind;
  if (kind !== "bool" && kind !== "choice") props.settings.edit(key, text);
}
watch(modem, (wanted) => wanted && send({ cmd: "list_ports" }));
</script>

<template>
  <SettingsField
    v-if="keys.includes(TRANSMIT_KEY)"
    :id="fieldId(TRANSMIT_KEY)"
    :info="info(TRANSMIT_KEY)"
    :model-value="valueFor(TRANSMIT_KEY, settings.draft)"
    :fallback="defaults[TRANSMIT_KEY] ?? ''"
    :error="settings.errors[TRANSMIT_KEY] ?? ''"
    :changed="form.changed(TRANSMIT_KEY)"
    :apply="true"
    @update:model-value="typed(TRANSMIT_KEY, $event)"
    @choose="form.choose({ [TRANSMIT_KEY]: storedFor(TRANSMIT_KEY, settings.draft, $event) })"
  />
  <RadioStatus :tnc="tnc" :now="now" :open="unconnected">
    <template v-for="key in keys.filter((k) => k !== TRANSMIT_KEY)" :key="key">
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
        <template v-if="key === KEYING_KEY && (settings.draft[key] ?? '') === '' && chosenKeying !== ''" #after>
          <span class="muted port-found">{{ t("settings.port.found", { port: chosenKeying }) }}</span>
        </template>
      </SettingsField>
    </template>
    <FindRadioRow id="find-radio" />
  </RadioStatus>
</template>
