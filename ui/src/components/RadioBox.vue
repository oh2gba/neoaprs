<script setup lang="ts">
// The box of one radio in the Radio group of the Settings tab (and of the setup guide's Radio step): a box with the radio's legend (while it is named, the name typed; else the box's word of its kind: "FM radio", "HF radio 2") that folds by its arrow, kept in
// this browser by the radio (`settings.fold.radio-3`). In it, in this order:
// - Enable, its tickbox, with the (i) of its kind; greyed while it is the only radio on (`only`), since a station keeps one radio on; a tick on its way is told to the group (`pending`), so that the others' follow at once;
// - while the station has several radios (`named`; a station of one radio has the box it always had), Name and Remove, outside the status, so that a radio that is off can be renamed and removed: the Name's placeholder is what the radio is called without one
//   ("HF 2"), a name is sent when the field is left or Enter is pressed (`radio_change`; one that another radio is called by is refused here in the daemon's words), and Remove asks twice (`radio_remove`), and is off for the only radio on;
// - while the radio is on, its status line (RadioStatus) and behind its arrow the Radio type (the types of its kind), the type's fields (SettingsRadioFields) and what the type can do: the suggested frequencies, Find my radio,
//   and with `tools` (the Settings tab; the guide leaves them out) Tune, the transmit level and the scope.
// A radio is worked by its own settings (`radio/3/port`), `radio_change` for its Enable, type and name, and told by its row of the topic `radios`. The daemon's
// refusal of a change of the radio stands under the field it is about (its coded text), in the box that asked last (the refusal names no radio), and what was chosen stays shown until the radio's row says it or the
// daemon refuses it (a change that could not be sent, or whose answer the lost connection took, shows the daemon's again at once). The fold opens by itself while the radio is on and not connected, for a complaint about one of its fields, and for a refusal; the page leads to a box by lib/attention.ts (the radio just added). The
// box says which radio it is to what is pressed inside it (`data-radio`, the name while several radios are on, the type): Find my radio searches for that radio. Its ids and its fold are the place's (lib/settingsradio.ts BOX_IDS: the setup
// guide's Radio step shows the same boxes while the Settings tab's are on the page too).
import { computed, nextTick, ref, watch } from "vue";
import FindRadioRow from "@/components/FindRadioRow.vue";
import HfFrequencies from "@/components/HfFrequencies.vue";
import HfLevelRow from "@/components/HfLevelRow.vue";
import HfScope from "@/components/HfScope.vue";
import HfTuneRow from "@/components/HfTuneRow.vue";
import RadioStatus from "@/components/RadioStatus.vue";
import SoundCardLevel from "@/components/SoundCardLevel.vue";
import SettingsBox from "@/components/SettingsBox.vue";
import SettingsField from "@/components/SettingsField.vue";
import SettingsRadioFields from "@/components/SettingsRadioFields.vue";
import TwoWords from "@/components/TwoWords.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import type { Settings } from "@/composables/useSettings";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { useSure } from "@/composables/useSure";
import { t } from "@/i18n";
import { errorReason } from "@/i18n/errortext";
import { KIND_WORDS, typeOf, type PageRadio } from "@/lib/radios";
import { FIELDS, type FieldInfo } from "@/lib/settings";
import { askedOn, boxIds, boxKeys, boxTitle, radioElementId, typeChoices, unnamed, type Asked } from "@/lib/settingsradio";
import { LIMITS } from "@/protocol/lists";
import type { RadioChangeCommand } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{
    radio: PageRadio;
    settings: Settings;
    form: SettingsFormState;
    defaults: Record<string, string>;
    /** the station has several radios: the box has Name and Remove, and its legend is the name typed */
    named?: boolean;
    /** it is the only radio on: its Enable is greyed and its Remove off */
    only?: boolean;
    /** Tune, the transmit level and the scope (the guide leaves them out) */
    tools?: boolean;
  }>(),
  { named: false, only: false, tools: true },
);
/** `pending`: the tick of the radio on its way to the daemon (null once it is told back or refused). */
const emit = defineEmits<{ pending: [enabled: boolean | null] }>();
const context = useDaemonContext();
const { send, now, lastError, connection, status } = context;
const radios = useRadios();
/** The ids of the place the box is in (the Settings tab's, or the setup guide's: lib/settingsradio.ts BOX_IDS). */
const ids = boxIds();

/** What the operator changed and the daemon has not told back yet: the tick, the type, the name. Each is shown until the radio's row says it or it is refused. */
const pending = ref<{ enabled?: boolean; type?: PageRadio["type"]; name?: string }>({});
const enabled = computed(() => pending.value.enabled ?? props.radio.enabled);
const type = computed(() => pending.value.type ?? props.radio.type);
const connected = computed(() => props.radio.row.state === "connected");
const fields = computed(() => boxKeys({ ...props.radio, type: type.value }));
const can = computed(() => props.radio.row.can);
/** Find my radio is in the box of a radio with a serial line (plan section 6a). */
const findable = computed(() => can.value.find);

/** The change of a radio the page asked last (one for the page), and the daemon's refusal of it under its field. */
type Part = Asked["part"];
const asked = askedOn(context);
const refusal = ref<{ part: Part; text: string } | null>(null);
function change(part: Part, values: Omit<RadioChangeCommand, "cmd" | "radio">): void {
  refusal.value = null;
  asked.value = { radio: props.radio.id, part };
  pending.value = { ...pending.value, [part]: values[part] };
  // not sent: the toast says not connected, and the box shows the daemon's again (once the change has been drawn, so that the control the operator worked is drawn back)
  if (!send({ cmd: "radio_change", radio: props.radio.id, ...values })) void nextTick(() => settle(part));
}
function settle(part: Part): void {
  const { [part]: _gone, ...rest } = pending.value;
  pending.value = rest;
  if (asked.value?.radio === props.radio.id && asked.value.part === part) asked.value = null;
}
watch(lastError, (toast) => {
  const mine = asked.value;
  if (toast === null || toast.cmd !== "radio_change" || mine?.radio !== props.radio.id) return;
  refusal.value = { part: mine.part, text: errorReason(toast, radios) };
  settle(mine.part);
});
// the row says what was asked: what is shown is the daemon's again (a row that changes for anything else, its state, keeps what was chosen)
watch(
  () => props.radio,
  (radio) => {
    const asking = pending.value;
    if (asking.enabled !== undefined && radio.enabled === asking.enabled) settle("enabled");
    if (asking.type !== undefined && radio.type === asking.type) settle("type");
    if (asking.name !== undefined && radio.row.name === asking.name) settle("name");
  },
);
// a change lost with the connection is never told back: the box shows the daemon's again, and the radios the daemon tells when it is back say what is in force
watch(connection, (state) => {
  if (state !== "open") for (const part of ["enabled", "type", "name"] as const) if (pending.value[part] !== undefined) settle(part);
});
watch(
  () => pending.value.enabled,
  (tick) => emit("pending", tick ?? null),
);
const refused = (part: Part): string => (refusal.value?.part === part ? refusal.value.text : "");

/** The Enable of the radio: the words and the (i) of its kind's Enable; of a type that only listens, an (i) that says so in place of what its kind sends. */
const enableInfo = computed<FieldInfo>(() => {
  const own = FIELDS[`${props.radio.kind}/enabled`] ?? { label: t("settings.enable.label"), kind: "bool" };
  const kind = typeOf(props.radio)?.can.transmit === false ? { ...own, tip: [t("settings.rx_enabled.tip1"), t("settings.fm_enabled.tip2")] } : own;
  return props.only ? { ...kind, title: t("settings.enable.only_radio_title") } : kind;
});
function tick(text: string): void {
  change("enabled", { enabled: text === "true" });
}

/** The Radio type of the radio: the types of its kind, with the (i) of the one list. */
const typeInfo = computed<FieldInfo>(() => ({
  ...(FIELDS[props.radio.kind === "hf" ? "hf/profile" : "tnc/profile"] ?? { label: t("settings.profile.label") }),
  kind: "choice",
  choices: typeChoices(props.radio.kind, status.value?.unavailable_types),
}));
function choose(key: string): void {
  const chosen = typeOf({ type: key })?.key;
  if (chosen === undefined || chosen === props.radio.type) return;
  change("type", { type: chosen });
}

/** The Name: what is typed, sent when the field is left or Enter is pressed; it follows the daemon while it is not being edited. */
const name = ref(props.radio.row.name);
const nameProblem = ref("");
watch(
  () => props.radio.row.name,
  (now, before) => {
    if (name.value === before) name.value = now;
  },
);
const max = LIMITS.radio.nameMax;
const nameInfo = computed<FieldInfo>(() => ({
  label: t("radio.name"),
  maxLength: max,
  empty: unnamed(props.radio),
  tipLabel: t("radio.name.tip_label"),
  tip: [t("radio.name.tip1")],
}));
/** Whether another radio of the station is called by this name already (its name or, without one, its label "FM 2"), case folded as the daemon compares names. */
const taken = (typed: string): boolean =>
  typed !== "" && radios.all.value.some((other) => !other.removed && other.id !== props.radio.id && other.name.toLowerCase() === typed.toLowerCase());
/** Whether a name is in the form of the label of a radio with no name of its own: a word of a kind as the catalogue has it (FM, Mercury, LoRa: the same in every language), alone or with a space and a number
 * ("FM 2"), case folded (the daemon refuses these itself: `radio.name_label`). The name of a band ("HF", "20 m") is no kind's word and is taken. */
const labelLike = (typed: string): boolean => {
  const folded = typed.toLowerCase().replace(/ \d+$/, "");
  return Object.values(KIND_WORDS).some((id) => t(id).toLowerCase() === folded);
};
function rename(): void {
  const typed = name.value.trim();
  if (typed === props.radio.row.name) return void (name.value = typed);
  if (typed.length > max || !/^[\x20-\x7e]*$/.test(typed)) return void (nameProblem.value = t("error.radio.name_form", { name: typed, max }));
  if (taken(typed)) return void (nameProblem.value = t("error.radio.name_taken", { name: typed }));
  if (labelLike(typed)) return void (nameProblem.value = t("error.radio.name_label", { name: typed }));
  nameProblem.value = "";
  name.value = typed;
  change("name", { name: typed });
}
function unrename(): void {
  name.value = props.radio.row.name;
  nameProblem.value = "";
  if (refusal.value?.part === "name") refusal.value = null;
}
function typing(text: string): void {
  name.value = text;
  nameProblem.value = "";
  if (refusal.value?.part === "name") refusal.value = null;
}

const sure = useSure<"remove">();
const remove = (): void => sure.press("remove", () => send({ cmd: "radio_remove", radio: props.radio.id }));

/** The box opens by itself: the radio is on and not connected, the daemon complains about one of its fields or asks about one, or a change of it was refused. */
const look = computed(() => {
  const mine = fields.value;
  return (
    (enabled.value && !connected.value) ||
    mine.some((key) => (props.settings.errors[key] ?? "") !== "" || props.form.question.value?.key === key) ||
    refusal.value !== null ||
    nameProblem.value !== ""
  );
});
const foldId = computed(() => ids(`radio-${props.radio.id}`));
const gainKey = computed(() => `radio/${props.radio.id}/tx_gain_db`);
const hasGain = computed(() => can.value.tx_gain && gainKey.value in props.settings.values.value);
</script>

<template>
  <SettingsBox
    :title="boxTitle(radio, named)"
    :fold-id="foldId"
    :show="look"
    :data-radio="radio.id"
    :data-radio-name="radios.several.value ? radio.name : undefined"
    :data-radio-type="type"
  >
    <SettingsField
      :id="ids(radioElementId(radio, 'enabled'))"
      :info="enableInfo"
      :model-value="String(enabled)"
      fallback=""
      :error="refused('enabled')"
      :changed="false"
      :apply="true"
      :disabled="only"
      @choose="tick"
    />
    <SettingsField
      v-if="named"
      :id="ids(radioElementId(radio, 'name'))"
      class="radioname"
      :info="nameInfo"
      :model-value="name"
      fallback=""
      :error="nameProblem || refused('name')"
      :changed="name !== radio.row.name"
      :apply="true"
      @update:model-value="typing"
      @commit="rename"
      @cancel="unrename"
    >
      <template #after>
        <button
          :id="ids(radioElementId(radio, 'remove'))"
          class="btn"
          :class="{ danger: sure.armed.value === 'remove' }"
          type="button"
          :disabled="only"
          @click="remove"
        >
          <TwoWords :second="sure.armed.value === 'remove'">
            <template #first>{{ t("radio.remove") }}</template>
            <template #second>{{ t("radio.remove_sure") }}</template>
          </TwoWords>
        </button>
      </template>
    </SettingsField>
    <RadioStatus v-if="enabled" :row="radio.row" :now="now" :open="!connected">
      <SettingsField
        :id="ids(radioElementId(radio, 'type'))"
        :info="typeInfo"
        :model-value="type"
        fallback=""
        :error="refused('type')"
        :changed="false"
        :apply="true"
        @choose="choose"
      />
      <SettingsRadioFields :keys="fields" :settings="settings" :form="form" :defaults="defaults" :radio="radio" />
      <HfFrequencies v-if="can.frequencies && radio.row.modem" :radio="radio" />
      <FindRadioRow v-if="findable" :id="ids(radioElementId(radio, 'find'))" />
      <template v-if="tools">
        <HfTuneRow v-if="can.tune" :id="ids(radioElementId(radio, 'tune'))" :radio="radio" />
        <SoundCardLevel v-if="can.rx_level" :radio="radio" :form="form" />
        <HfLevelRow v-if="hasGain" :id="ids(radioElementId(radio, 'txlevel'))" :settings="settings" :form="form" :radio="radio" :setting-key="gainKey" />
        <HfScope v-if="can.scope" :radio="radio.id" :card="{ radio, form }" />
      </template>
    </RadioStatus>
  </SettingsBox>
</template>
