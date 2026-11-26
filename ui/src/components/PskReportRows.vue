<script setup lang="ts">
// A Mercury radio's reports to PSK Reporter in its box: the tick (`radio/<id>/psk_report`) and the
// dial the radio is tuned to (`radio/<id>/psk_dial`), chosen as the HF tests form chooses one
// (DialChoice: a suggested dial of the box, or Other and the number). Empty until one is chosen;
// while the tick is off the dial is greyed and keeps its place. A choice is stored at once, a typed
// number when it is finished and is a dial; a stored dial the list no longer has shows as typed.
import { computed, ref } from "vue";
import DialChoice from "@/components/DialChoice.vue";
import SettingsField from "@/components/SettingsField.vue";
import type { Settings } from "@/composables/useSettings";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { t } from "@/i18n";
import type { PageRadio } from "@/lib/radios";
import type { FieldInfo } from "@/lib/settings";
import { boxIds, inputId } from "@/lib/settingsradio";
import { OTHER_DIAL, dialOfNumber, numberOfDial } from "@/lib/skeds";

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
const tickInfo = computed<FieldInfo>(() => ({ label: t("settings.psk_report.label"), kind: "bool" }));

function choose(value: string): void {
  if (value === OTHER_DIAL) return void (typing.value = typed.value ? dial.value : "");
  typing.value = null;
  props.form.choose({ [dialKey.value]: value });
}
function finish(): void {
  const found = typing.value === null ? null : dialOfNumber(typing.value);
  if (found === null) return;
  typing.value = null;
  if (found !== stored.value) props.form.choose({ [dialKey.value]: found });
}
</script>

<template>
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
    @choose="choose"
    @update:dial="typing = $event"
    @commit="finish"
  />
</template>
