<script setup lang="ts">
// The fields of one radio of the Radio group, each worked as in the form: a typed one is sent when it is left or Enter is pressed, a choice at once (the form's `settings` and `form`). An FM radio's are the type of TNC, the port (SettingsPort, with the port the search found beside it), the speed, or the host and port of a TNC reached over TCP;
// an HF radio's are its type, the sound card, a plain choice among what the daemon found (the system's name for each, its id the hover title; Refresh beside it), and the keying, a choice made of the ports the daemon lists (lib/mercury.ts), and beside the
// keying the Test button, which keys the radio for a second so that the operator sees it go to transmit and come back (composables/useHfTests.ts); the status line says Keyed meanwhile.
// Neither offers "find automatically": the daemon's proposal (`pick` of a sound card, `keying` of the ports message) is preselected and stored as the setting while it is empty, the card first and the keying once that is answered, so that
// the settings name a card and a keying as soon as the HF radio is on. (An empty setting stays legal for the daemon, and a station that has one runs as before; the page never offers it.)
// The keys are the settings of before for the radios of before (`serial/port`, `mercury/keying`), else the radio's own (`radio/3/port`, `radio/3/keying`): a field is known by the field of the radio it is (lib/settingsradio.ts `fieldOfKey`), and its id is
// its key's (`set-serial-port`, `set-radio-3-port`). Refresh asks the daemon for the ports of the radio of the box (`radio`, while the ports message does not say which radio it is for: one box at a time).
import { computed, watchEffect } from "vue";
import SettingsField from "@/components/SettingsField.vue";
import SettingsPort from "@/components/SettingsPort.vue";
import type { Settings } from "@/composables/useSettings";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useHfTests } from "@/composables/useHfTests";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { t } from "@/i18n";
import { keyingChoices, soundCardChoices, soundCardPick, soundCardWith } from "@/lib/mercury";
import type { PageRadio } from "@/lib/radios";
import { fieldFor, type FieldInfo } from "@/lib/settings";
import { togetherOf } from "@/lib/settinglinks";
import { boxIds, fieldOfKey, inputId, radioFieldOf } from "@/lib/settingsradio";
import { speedFallback } from "@/lib/tncprofile";
import type { Command } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{ keys: readonly string[]; settings: Settings; form: SettingsFormState; defaults: Record<string, string>; radio?: PageRadio | null }>(),
  {
    radio: null,
  },
);
const { config, send, ports } = useDaemonContext();
/** The ids of the place the fields are in (the Settings tab's, or the setup guide's: lib/settingsradio.ts BOX_IDS). */
const ids = boxIds();

/** Whether the key is a radio's own (`radio/3/port`), not a setting of before. */
const own = (key: string): boolean => radioFieldOf(key) !== null;
const isCard = (key: string): boolean => fieldOfKey(key) === "sound_card";
const isKeying = (key: string): boolean => fieldOfKey(key) === "keying";
const isPort = (key: string): boolean => fieldOfKey(key) === "port";
/** The type of TNC a speed's placeholder follows: the radio's own type, or the setting of before. */
const typeFor = (key: string): string | undefined => (own(key) ? props.radio?.type : props.settings.draft["tnc/profile"]);
const fallback = (key: string) => (fieldOfKey(key) === "baud" ? speedFallback(typeFor(key), defaultOf(key)) : defaultOf(key));
/** The default of a key, from the form's (the settings of before) or the radios' own. */
const defaultOf = (key: string): string => props.defaults[key] ?? props.settings.defaults.value[key] ?? "";
const cardKey = computed(() => props.keys.find(isCard));
const keyingKey = computed(() => props.keys.find(isKeying));
/** The daemon's proposals, which the field shows as chosen while the setting is empty and which the page then stores. */
const pick = (key: string): string => (isCard(key) ? soundCardPick(ports.value) : (ports.value?.keying ?? ""));
const valueOf = (key: string): string => (props.settings.draft[key] ?? "") || (isCard(key) || isKeying(key) ? pick(key) : "");
const cardInfo = computed<FieldInfo>(() => ({ ...fieldFor(cardKey.value ?? ""), kind: "choice", choices: soundCardChoices(ports.value) }));
const keyingInfo = computed<FieldInfo>(() => ({
  ...fieldFor(keyingKey.value ?? ""),
  kind: "choice",
  choices: keyingChoices(ports.value, valueOf(keyingKey.value ?? "")),
}));
const infoOf = (key: string): FieldInfo => (isCard(key) ? cardInfo.value : isKeying(key) ? keyingInfo.value : fieldFor(key));
/** The port the search found last, beside an automatic port: the daemon's memory of radio 1 (`serial/last_port`); another radio's is not told. */
const found = (key: string): string => (own(key) ? "" : (config.value?.values["serial/last_port"] ?? ""));
// An empty setting takes the proposal: the card first, the keying when nothing is out any more (the form sends one change at a time). A card stored as one of its two Windows devices becomes the whole card first.
watchEffect(() => {
  const card = cardKey.value;
  const stored = card === undefined ? "" : (props.settings.draft[card] ?? "");
  const whole = soundCardWith(ports.value, stored);
  if (card !== undefined && whole !== "" && props.settings.expected(card) === stored) {
    if (!props.settings.saving.value) props.form.choose({ [card]: whole });
    return;
  }
  for (const key of [cardKey.value, keyingKey.value]) {
    if (key === undefined) continue;
    const proposal = pick(key);
    if (proposal === "" || (props.settings.draft[key] ?? "") !== "" || props.settings.expected(key) !== "") continue;
    if (!props.settings.saving.value) props.form.choose({ [key]: proposal });
    break;
  }
});
const tests = useHfTests(() => props.radio);
/** A typed field follows the typing; a choice is made by `choose` (it also says the text it has, which is not typing). */
function typed(key: string, text: string): void {
  const kind = infoOf(key).kind;
  if (kind !== "bool" && kind !== "choice") props.settings.edit(key, text);
}
/** A typed field was finished: it is sent with the fields it is sent together with (the host and the port of a TNC over TCP, of before or a radio's own), unless focus only went to one of them, by the ids of the place. */
function finish(key: string, next: EventTarget | null): void {
  const together = togetherOf(key);
  const within = next instanceof Element && together.some((other) => other !== key && next.id === ids(inputId(other)));
  if (!within) props.settings.commit(together);
}
/** The ports again, for the radio of the box. */
function refresh(key: string): void {
  const id = radioFieldOf(key)?.id;
  const ask: Command = id === undefined ? { cmd: "list_ports" } : { cmd: "list_ports", radio: id };
  send(ask);
}
</script>

<template>
  <template v-for="key in keys" :key="key">
    <SettingsPort
      v-if="isPort(key)"
      :id="ids(inputId(key))"
      :info="fieldFor(key)"
      :model-value="settings.draft[key] ?? ''"
      :found="found(key)"
      :ports="ports"
      :error="settings.errors[key] ?? ''"
      :changed="form.changed(key)"
      @update:model-value="settings.edit(key, $event)"
      @choose="form.choose({ [key]: $event })"
      @commit="finish(key, $event)"
      @cancel="settings.cancel(key)"
      @refresh="refresh(key)"
    />
    <SettingsField
      v-else
      :id="ids(inputId(key))"
      :info="infoOf(key)"
      :model-value="valueOf(key)"
      :fallback="fallback(key)"
      :error="settings.errors[key] ?? ''"
      :changed="form.changed(key)"
      :apply="true"
      @update:model-value="typed(key, $event)"
      @choose="form.choose({ [key]: $event })"
      @commit="finish(key, $event)"
      @cancel="settings.cancel(key)"
    >
      <template v-if="isCard(key)" #after>
        <button class="btn" type="button" @click="refresh(key)">{{ t("settings.port.refresh") }}</button>
      </template>
      <template v-else-if="isKeying(key)" #after>
        <button
          :id="ids(own(key) ? `${inputId(key)}-test` : 'hf-key-test')"
          class="btn"
          type="button"
          :disabled="tests.testOff.value"
          :title="tests.why.value"
          @click="tests.keyTest"
        >
          {{ t("settings.keying.test") }}
        </button>
      </template>
    </SettingsField>
  </template>
</template>
