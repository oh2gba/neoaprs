<script setup lang="ts">
// The fields of one radio, each worked as in the form: a typed field is sent when left or on Enter,
// a choice at once. Packet radios have TNC type, port, speed or TCP host and port; HF radios have type,
// sound card and keying with a Test button (useHfTests), and an Address row under a keying through
// a rig program (flrig, rigctld), whose empty value is the program's own address on this computer.
// Where the daemon lists a sound server's devices, the sound card is two choices, the device recorded
// from and the one played to, stored as one setting (lib/mercury.ts soundCardJoin).
// The daemon's proposal for the sound card and keying (`pick`, `keying`) is preselected and stored
// while the setting is empty. Keys are the radio's own (`radio/3/port`). Sound cards and proposals
// are read from the answer for this radio only (`portsByRadio`). A proposal the daemon refused is
// not stored again from the same answer.
import { computed, ref, watchEffect } from "vue";
import SettingsField from "@/components/SettingsField.vue";
import SettingsPort from "@/components/SettingsPort.vue";
import type { Settings } from "@/composables/useSettings";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useHfTests } from "@/composables/useHfTests";
import { useRadios } from "@/composables/useRadios";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { t } from "@/i18n";
import {
  keyingChoices,
  rigAddress,
  rigDefault,
  rigKind,
  soundCardChoices,
  soundCardGone,
  soundCardHalfChoices,
  soundCardHalves,
  soundCardJoin,
  soundCardPick,
  soundCardSplit,
  soundCardWith,
  withAddress,
  type SoundHalf,
} from "@/lib/mercury";
import { holderOf } from "@/lib/portchoice";
import { typeOf, type PageRadio } from "@/lib/radios";
import { fieldFor, type FieldInfo } from "@/lib/settings";
import { togetherOf } from "@/lib/settinglinks";
import { boxIds, fieldOfKey, inputId, proposedFrom, proposing, radioFieldOf } from "@/lib/settingsradio";
import { speedFallback } from "@/lib/tncprofile";
import type { Command, PortsMessage } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{
    keys: readonly string[];
    settings: Settings;
    form: SettingsFormState;
    defaults: Record<string, string>;
    radio?: PageRadio | null;
  }>(),
  {
    radio: null,
  },
);
const { config, send, ports, portsByRadio } = useDaemonContext();
/** The ids of the place the fields are in (the Settings tab or the setup guide). */
const ids = boxIds();
const radios = useRadios();
/** Who holds a port or a card: another radio by name, the GPS receiver by its word. */
const holder = computed(() => holderOf(props.radio?.id ?? -1, (id) => radios.byId(id)?.name));

const isCard = (key: string): boolean => fieldOfKey(key) === "sound_card";
const isKeying = (key: string): boolean => fieldOfKey(key) === "keying";
const isPort = (key: string): boolean => fieldOfKey(key) === "port";
/** A speed's placeholder follows the radio's TNC type. */
const fallback = (key: string) =>
  fieldOfKey(key) === "baud" ? speedFallback(props.radio?.type, defaultOf(key)) : defaultOf(key);
/** The default of a key, from the form or the settings. */
const defaultOf = (key: string): string => props.defaults[key] ?? props.settings.defaults.value[key] ?? "";
const cardKey = computed(() => props.keys.find(isCard));
const keyingKey = computed(() => props.keys.find(isKeying));
/** The answer to `list_ports` for this radio (null until one came). */
const own = computed<PortsMessage | null>(() =>
  props.radio === null ? null : (portsByRadio.value.get(props.radio.id) ?? null),
);
/** The daemon's proposals, shown as chosen while the setting is empty and then stored. */
const pick = (key: string): string => (isCard(key) ? soundCardPick(own.value) : (own.value?.keying ?? ""));
const valueOf = (key: string): string =>
  (props.settings.draft[key] ?? "") || (isCard(key) || isKeying(key) ? pick(key) : "");
const cardInfo = computed<FieldInfo>(() => ({
  ...fieldFor(cardKey.value ?? ""),
  kind: "choice",
  choices: soundCardChoices(own.value, holder.value, props.settings.expected(cardKey.value ?? "")),
}));
/** Whether the sound is chosen as two devices (a sound server's are listed). */
const split = computed(() => soundCardSplit(own.value));
const HALVES: readonly SoundHalf[] = ["capture", "playback"];
const halfOf = (key: string, half: SoundHalf): string => soundCardHalves(valueOf(key))[half === "capture" ? 0 : 1];
/** The field of one half: its own label and devices; the (i) is the first field's alone. */
function halfInfo(half: SoundHalf): FieldInfo {
  const { tip, tipLabel, picture, ...plain } = fieldFor(cardKey.value ?? "");
  const current = soundCardHalves(props.settings.expected(cardKey.value ?? ""))[half === "capture" ? 0 : 1];
  return {
    ...(half === "capture"
      ? { ...plain, ...(tip ? { tip } : {}), ...(tipLabel ? { tipLabel } : {}), ...(picture ? { picture } : {}) }
      : plain),
    label: t(`settings.sound_card.${half}`),
    kind: "choice",
    choices: soundCardHalfChoices(own.value, half, holder.value, current),
    other: soundCardGone,
  };
}
function chooseHalf(key: string, half: SoundHalf, value: string): void {
  const [capture, playback] = soundCardHalves(valueOf(key));
  props.form.choose({ [key]: half === "capture" ? soundCardJoin(value, playback) : soundCardJoin(capture, value) });
}
/**
 * The USB group of the radio's sound card (`usb_group`), which orders the keying ports; null if
 * unknown.
 */
const cardGroup = computed<string | null>(() => {
  const now = valueOf(cardKey.value ?? "");
  const id = soundCardWith(own.value, now) || now;
  const [capture] = soundCardHalves(id);
  return own.value?.sound_cards.find((c) => c.id === id || c.id === capture)?.usb_group ?? null;
});
const keyingInfo = computed<FieldInfo>(() => ({
  ...fieldFor(keyingKey.value ?? ""),
  kind: "choice",
  choices: keyingChoices(ports.value, valueOf(keyingKey.value ?? ""), cardGroup.value),
}));
/** The rig program the keying names, "" for a keying by a line, a chip or VOX. */
const rig = (key: string): string => rigKind(valueOf(key));
/** The address as it is typed; null while the keying's own is shown. */
const addressDraft = ref<string | null>(null);
const addressOf = (key: string): string => addressDraft.value ?? rigAddress(valueOf(key));
const addressInfo = computed<FieldInfo>(() => ({ label: t("settings.keying.address") }));
function commitAddress(key: string): void {
  const typed = addressOf(key);
  addressDraft.value = null;
  if (typed.trim() !== rigAddress(valueOf(key))) props.form.choose({ [key]: withAddress(rig(key), typed) });
}
/** A field's words: the kind's own where they differ. */
const wordsOf = (key: string): FieldInfo => fieldFor(key, {}, props.radio?.kind);
const infoOf = (key: string): FieldInfo =>
  isCard(key) ? cardInfo.value : isKeying(key) ? keyingInfo.value : wordsOf(key);
/**
 * The port the search found last, shown beside an automatic port (`serial/last_port`, radio 1
 * only).
 */
const found = (key: string): string =>
  radioFieldOf(key)?.id === 1 ? (config.value?.values["serial/last_port"] ?? "") : "";
/** Whether the proposal was already stored from this answer and refused (its key has an error). */
const refusedAgain = (key: string, value: string): boolean =>
  own.value !== null && proposedFrom(own.value, key, value) && (props.settings.errors[key] ?? "") !== "";
function store(key: string, value: string): void {
  if (props.settings.saving.value || refusedAgain(key, value)) return;
  if (own.value !== null) proposing(own.value, key, value);
  props.form.choose({ [key]: value });
}
// An empty setting takes the proposal: the card first, then the keying once nothing is pending.
// A card stored as one of its two Windows devices becomes the whole card first.
watchEffect(() => {
  const card = cardKey.value;
  const now = card === undefined ? "" : (props.settings.draft[card] ?? "");
  const whole = soundCardWith(own.value, now);
  if (card !== undefined && whole !== "" && props.settings.expected(card) === now) return store(card, whole);
  for (const key of [cardKey.value, keyingKey.value]) {
    if (key === undefined) continue;
    const proposal = pick(key);
    if (proposal === "" || (props.settings.draft[key] ?? "") !== "" || props.settings.expected(key) !== "") continue;
    store(key, proposal);
    break;
  }
});
const tests = useHfTests(() => props.radio);
/** A typed field follows the typing; a choice is made by `choose`. */
function typed(key: string, text: string): void {
  const kind = infoOf(key).kind;
  if (kind !== "bool" && kind !== "choice") props.settings.edit(key, text);
}
/**
 * A typed field is finished: it is sent with the fields it belongs to, unless focus only moved to
 * one of them.
 */
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
      :info="wordsOf(key)"
      :model-value="settings.draft[key] ?? ''"
      :found="found(key)"
      :unset="props.radio !== null && typeOf(props.radio)?.can.find === false"
      :ports="ports"
      :holder="holder"
      :error="settings.errors[key] ?? ''"
      :changed="form.changed(key)"
      @update:model-value="settings.edit(key, $event)"
      @choose="form.choose({ [key]: $event })"
      @commit="finish(key, $event)"
      @cancel="settings.cancel(key)"
      @refresh="refresh(key)"
    />
    <template v-else-if="isCard(key) && split">
      <SettingsField
        v-for="half in HALVES"
        :id="ids(`${inputId(key)}-${half}`)"
        :key="half"
        :info="halfInfo(half)"
        :model-value="halfOf(key, half)"
        fallback=""
        :error="half === 'playback' ? (settings.errors[key] ?? '') : ''"
        :changed="form.changed(key)"
        :apply="true"
        @choose="chooseHalf(key, half, $event)"
        @commit="finish(key, $event)"
        @cancel="settings.cancel(key)"
      >
        <template v-if="half === 'capture'" #after>
          <button class="btn" type="button" @click="refresh(key)">{{ t("settings.port.refresh") }}</button>
        </template>
      </SettingsField>
    </template>
    <SettingsField
      v-else
      :id="ids(inputId(key))"
      :info="infoOf(key)"
      :model-value="valueOf(key)"
      :fallback="fallback(key)"
      :error="isKeying(key) && rig(key) !== '' ? '' : (settings.errors[key] ?? '')"
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
          :id="ids(`${inputId(key)}-test`)"
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
    <SettingsField
      v-if="isKeying(key) && rig(key) !== ''"
      :id="ids(`${inputId(key)}-address`)"
      :info="addressInfo"
      :model-value="addressOf(key)"
      :fallback="rigDefault(rig(key))"
      :error="settings.errors[key] ?? ''"
      :changed="false"
      :apply="true"
      @update:model-value="addressDraft = $event"
      @commit="commitAddress(key)"
      @cancel="addressDraft = null"
    />
  </template>
</template>
