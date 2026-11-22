<script setup lang="ts">
// The box of one radio in the Radio group (also in the setup guide), folding by its arrow.
// It holds, in order: Enable, Name and Remove (when the station has several radios), the status
// line, and behind the arrow the type, its fields and what the type can do.
// Settings are the radio's own (`radio/3/port`); `radio_change` sends Enable, type and name.
// The daemon's refusal appears under the field it is about, in the box that asked last.
// Ids and fold state come from lib/settingsradio.ts BOX_IDS.
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
import { isPrintable } from "@/lib/messages";
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
    /**
     * the station has several radios: the box has Name and Remove, and its legend is the name typed
     */
    named?: boolean;
    /** it is the only radio on: its Enable is greyed and its Remove off */
    only?: boolean;
    /** Tune, the transmit level and the scope (the guide leaves them out) */
    tools?: boolean;
  }>(),
  { named: false, only: false, tools: true },
);
/** `pending`: the tick of the radio on its way to the daemon (null once answered or refused). */
const emit = defineEmits<{ pending: [enabled: boolean | null] }>();
const context = useDaemonContext();
const { send, now, lastError, connection, status } = context;
const radios = useRadios();
/** The ids of the place the box is in (the Settings tab or the setup guide). */
const ids = boxIds();

/** What the operator changed and the daemon has not confirmed yet: the tick, the type, the name. */
const pending = ref<{ enabled?: boolean; type?: PageRadio["type"]; name?: string }>({});
const enabled = computed(() => pending.value.enabled ?? props.radio.enabled);
const type = computed(() => pending.value.type ?? props.radio.type);
const connected = computed(() => props.radio.row.state === "connected");
const fields = computed(() => boxKeys({ ...props.radio, type: type.value }));
const can = computed(() => props.radio.row.can);
/** Find my radio is offered for a radio with a serial line. */
const findable = computed(() => can.value.find);

/** The change the page asked last, and the daemon's refusal of it. */
type Part = Asked["part"];
const asked = askedOn(context);
const refusal = ref<{ part: Part; text: string } | null>(null);
function change(part: Part, values: Omit<RadioChangeCommand, "cmd" | "radio">): void {
  refusal.value = null;
  asked.value = { radio: props.radio.id, part };
  pending.value = { ...pending.value, [part]: values[part] };
  // not sent: the box shows the daemon's value again once the change has been drawn
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
// the row confirms what was asked: show the daemon's value again
watch(
  () => props.radio,
  (radio) => {
    const asking = pending.value;
    if (asking.enabled !== undefined && radio.enabled === asking.enabled) settle("enabled");
    if (asking.type !== undefined && radio.type === asking.type) settle("type");
    if (asking.name !== undefined && radio.row.name === asking.name) settle("name");
  },
);
// a change lost with the connection is never confirmed: show the daemon's value again
watch(connection, (state) => {
  if (state !== "open") for (const part of ["enabled", "type", "name"] as const) if (pending.value[part] !== undefined) settle(part);
});
watch(
  () => pending.value.enabled,
  (tick) => emit("pending", tick ?? null),
);
const refused = (part: Part): string => (refusal.value?.part === part ? refusal.value.text : "");

/** The Enable of the radio, with the (i) of its kind; a listen-only type has its own (i). */
const enableInfo = computed<FieldInfo>(() => {
  const own = FIELDS[`${props.radio.kind}/enabled`] ?? { label: t("settings.enable.label"), kind: "bool" };
  const kind = typeOf(props.radio)?.can.transmit === false ? { ...own, tip: [t("settings.rx_enabled.tip1"), t("settings.fm_enabled.tip2")] } : own;
  return props.only ? { ...kind, title: t("settings.enable.only_radio_title") } : kind;
});
function tick(text: string): void {
  change("enabled", { enabled: text === "true" });
}

/** The Radio type of the radio: the types of its kind. */
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

/**
 * The Name: sent when the field is left or Enter is pressed; follows the daemon while not edited.
 */
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
/** Whether another radio already has this name (or, without one, this label), case folded. */
const taken = (typed: string): boolean =>
  typed !== "" && radios.all.value.some((other) => !other.removed && other.id !== props.radio.id && other.name.toLowerCase() === typed.toLowerCase());
/**
 * Whether a name has the form of an unnamed radio's label (a kind word alone or with a number, case
 * folded). The daemon refuses these too (`radio.name_label`); a band name such as "20 m" is a name.
 */
const labelLike = (typed: string): boolean => {
  const folded = typed.toLowerCase().replace(/ \d+$/, "");
  return Object.values(KIND_WORDS).some((id) => t(id).toLowerCase() === folded);
};
function rename(): void {
  const typed = name.value.trim();
  if (typed === props.radio.row.name || typed === pending.value.name) return void (name.value = typed);
  if (typed.length > max || !isPrintable(typed)) return void (nameProblem.value = t("error.radio.name_form", { name: typed, max }));
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

/**
 * The box opens by itself when the radio is on and not connected, or a field has a complaint or a
 * refusal.
 */
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
