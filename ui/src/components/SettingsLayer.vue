<script setup lang="ts">
// A row of Settings, Map that belongs to a layer of the map: the list of sources of Aircraft or of Ships (the sources the daemon offers, `layer.offered`, in its order; a stored source that is not among them shows as None), or the receiver's address, which is there only
// while the row's choice is an own receiver (a Radarcape, tar1090 or dump1090, or for ships My own receiver; a Radarcape's box has its own (i)), with the state of the receiver under it as a GPS receiver's state is shown (a pill and one line, the flat row of StatusFold: it has nothing behind it, so it is StatusLine alone; the words of lib/receiverstatus.ts). The field is SettingsField, so the label, the (i), the input, the
// complaint under it and the events are the other rows'. A receiver that has not said yet is looking, so the row's room is there from the first moment.
import { computed } from "vue";
import SettingsField from "@/components/SettingsField.vue";
import StatusLine from "@/components/StatusLine.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { addressField, layerKey, layerOf, shownSource, sourceChoices } from "@/lib/layersettings";
import { receiverLook } from "@/lib/receiverstatus";
import { fieldFor, type FieldInfo } from "@/lib/settings";

const props = defineProps<{
  id: string;
  /** the setting's key: map/aircraft, map/aircraft_host, map/ships or map/ships_host */
  fieldKey: string;
  form: SettingsFormState;
}>();

const { settings, map, now } = useDaemonContext();
const { draft, errors } = settings;
const own = computed(() => layerKey(props.fieldKey));
/** The layer's row of the topic `map`. */
const layer = computed(() => (own.value ? layerOf(map.value?.layers, own.value.layer) : null));
const model = computed(() => draft[props.fieldKey] ?? "");
const isSource = computed(() => own.value?.role === "source");
/** The field: a source row has the sources offered; the address row its own words. */
const info = computed<FieldInfo>(() => {
  const base = fieldFor(props.fieldKey);
  if (!own.value) return base;
  return isSource.value ? { ...base, choices: sourceChoices(own.value.layer, layer.value?.offered) } : addressField(base, props.fieldKey, draft);
});
const shown = computed(() => (isSource.value && own.value ? shownSource(model.value, layer.value?.offered, own.value.layer) : model.value));
const look = computed(() => (own.value ? receiverLook(own.value.layer, layer.value?.receiver ?? null, now.value) : null));
/** A typed address follows the typing; a choice is made by `choose`. */
const typed = (text: string): void => {
  if (!isSource.value) settings.edit(props.fieldKey, text);
};
</script>

<template>
  <SettingsField
    :id="id"
    :info="info"
    :model-value="shown"
    fallback=""
    :error="errors[fieldKey] ?? ''"
    :changed="form.changed(fieldKey)"
    :apply="true"
    @update:model-value="typed"
    @choose="form.choose({ [fieldKey]: $event })"
    @commit="form.finish(fieldKey, $event)"
    @cancel="settings.cancel(fieldKey)"
  />
  <div v-if="!isSource && look" class="receiverstatus statusfold statushead statusflat">
    <StatusLine :state="look.state" :tone="look.tone" :line="look.line" />
  </div>
</template>
