<script setup lang="ts">
// A Mercury radio's reports to PSK Reporter, a box of its own (SettingsBox) at the end of its box: Enable (`radio/<id>/psk_report`) and the
// dial the radio is tuned to (`radio/<id>/psk_dial`), chosen as the HF tests form chooses one
// (DialChoice: a suggested dial of the box, or Other and the number). Empty until one is chosen;
// while the tick is off the dial is greyed and keeps its place. What the box shows is what is stored:
// a choice at once, Other with no number yet or a number that is no dial (below LIMITS.radio.dialMinMhz
// too) as an empty dial, a number that is one when it is finished. A stored dial the list no longer
// has shows as Other with its number.
import { computed, ref } from "vue";
import DialChoice from "@/components/DialChoice.vue";
import SettingsBox from "@/components/SettingsBox.vue";
import SettingsField from "@/components/SettingsField.vue";
import type { Settings } from "@/composables/useSettings";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { t } from "@/i18n";
import type { PageRadio } from "@/lib/radios";
import type { FieldInfo } from "@/lib/settings";
import { boxIds, inputId } from "@/lib/settingsradio";
import { OTHER_DIAL, dialAtLeast, numberOfDial } from "@/lib/skeds";
import { LIMITS } from "@/protocol/lists";

const props = defineProps<{ radio: PageRadio; settings: Settings; form: SettingsFormState }>();
const ids = boxIds();
const tickKey = computed(() => `radio/${props.radio.id}/psk_report`);
const dialKey = computed(() => `radio/${props.radio.id}/psk_dial`);
const on = computed(() => (props.settings.draft[tickKey.value] ?? "") === "true");
const frequencies = computed(() => props.radio.row.modem?.frequencies ?? []);
const stored = computed(() => props.settings.draft[dialKey.value] ?? "");
/** The number being typed after Other was chosen; null while the box shows the stored dial. */
const typing = ref<string | null>(null);
const typed = computed(
  () => typing.value !== null || (stored.value !== "" && !frequencies.value.some((f) => f.dial === stored.value)),
);
const dial = computed(() => typing.value ?? (typed.value ? numberOfDial(stored.value) : stored.value));
const tickInfo = computed<FieldInfo>(() => ({
  label: t("settings.enable.label"),
  name: t("settings.psk_report.box"),
  kind: "bool",
  tipLabel: t("settings.psk_report.tip_label"),
  tip: [t("settings.psk_report.tip1")],
}));

const least = LIMITS.radio.dialMinMhz;
function store(value: string): void {
  if (value !== stored.value) props.form.choose({ [dialKey.value]: value });
}
function choose(value: string): void {
  if (value !== OTHER_DIAL) {
    typing.value = null;
    return store(value);
  }
  typing.value = typed.value ? dial.value : "";
  store(dialAtLeast(typing.value, least) ?? "");
}
/** The number is finished: stored if it is a dial, else the dial is emptied; the field keeps its row. */
function finish(): void {
  if (typing.value === null) return;
  const found = dialAtLeast(typing.value, least);
  if (found !== null) typing.value = numberOfDial(found);
  store(found ?? "");
}
</script>

<template>
  <SettingsBox class="pskbox" :title="t('settings.psk_report.box')">
    <SettingsField
      :id="ids(inputId(tickKey))"
      :info="tickInfo"
      :model-value="String(on)"
      fallback=""
      :error="settings.errors[tickKey] ?? ''"
      :changed="form.changed(tickKey)"
      :apply="true"
      @choose="form.choose({ [tickKey]: $event })"
    />
    <DialChoice
      :id="ids(inputId(dialKey))"
      :dial-id="ids(`${inputId(dialKey)}-number`)"
      :frequencies="frequencies"
      :typed="typed"
      :dial="dial"
      :disabled="!on"
      :apply="true"
      :blank="true"
      :least="least"
      @choose="choose"
      @update:dial="typing = $event"
      @commit="finish"
    />
  </SettingsBox>
</template>
