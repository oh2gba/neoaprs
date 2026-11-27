<script setup lang="ts">
// A row of a layer's box in Settings, Map: the Source list of Aircraft or Ships (`layer.offered`,
// in the daemon's order; a stored source not among them shows as None), or the receiver's address,
// shown only while the choice is an own receiver, with the receiver's state under it
// (lib/receiverstatus.ts). A receiver that has not answered yet is looking, so the room is reserved
// from the first moment. Or the Ships box's AISStream key: a masked field with a link beside it to
// the page where a key is made, and under it a status row that says AISStream's refusal of the key,
// the room of both kept while there is nothing to say. Choosing a source switches the layer on in
// this browser's Layers box.
import { computed } from "vue";
import SettingsField from "@/components/SettingsField.vue";
import StatusLine from "@/components/StatusLine.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useMapLayers } from "@/composables/useMapLayers";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { t } from "@/i18n";
import { addressField, keyShown, layerKey, layerOf, shownSource, sourceChoices } from "@/lib/layersettings";
import { AISSTREAM_KEY_URL } from "@/lib/links";
import { receiverLook } from "@/lib/receiverstatus";
import { fieldFor, type FieldInfo } from "@/lib/settings";

const props = defineProps<{
  id: string;
  /** the setting's key: map/aircraft, map/aircraft_host, map/ships, map/ships_host or map/ships_key */
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
const isKey = computed(() => own.value?.role === "key");
/** The key's field is there while AISStream is chosen; else only its room. */
const keyOff = computed(() => isKey.value && !keyShown(draft));
const error = computed(() => errors[props.fieldKey] ?? "");
/** AISStream did not take the key: said in the status row under it, whose room is always kept. */
const refused = computed(() => isKey.value && !keyOff.value && layer.value?.problem === "key_refused");
/** The field: a source row has the sources offered; the address row its own words. */
const info = computed<FieldInfo>(() => {
  const base = fieldFor(props.fieldKey);
  if (!own.value) return base;
  return isSource.value
    ? { ...base, choices: sourceChoices(own.value.layer, layer.value?.offered) }
    : addressField(base, props.fieldKey, draft);
});
const shown = computed(() =>
  isSource.value && own.value ? shownSource(model.value, layer.value?.offered, own.value.layer) : model.value,
);
const look = computed(() =>
  own.value ? receiverLook(own.value.layer, layer.value?.receiver ?? null, now.value) : null,
);
const ticks = useMapLayers(map);
const choose = (value: string): void => {
  const layerId = own.value?.layer;
  if (isSource.value && layerId && value !== "none" && value !== shown.value) ticks.setTicked(layerId, true);
  props.form.choose({ [props.fieldKey]: value });
};
/** A typed address follows the typing; a choice is made by `choose`. */
const typed = (text: string): void => {
  if (!isSource.value) settings.edit(props.fieldKey, text);
};
</script>

<template>
  <SettingsField
    :id="id"
    :class="{ 'field-room': keyOff }"
    :info="info"
    :model-value="shown"
    fallback=""
    :error="error"
    :changed="form.changed(fieldKey)"
    :apply="true"
    :inert="keyOff || undefined"
    :aria-hidden="keyOff || undefined"
    @update:model-value="typed"
    @choose="choose"
    @commit="form.finish(fieldKey, $event)"
    @cancel="settings.cancel(fieldKey)"
  >
    <template v-if="isKey" #after>
      <a class="field-link" :href="AISSTREAM_KEY_URL" target="_blank" rel="noopener noreferrer">{{
        t("layers.aisstream.get_key")
      }}</a>
    </template>
  </SettingsField>
  <div v-if="!isSource && !isKey && look" class="receiverstatus statusfold statushead statusflat">
    <StatusLine :state="look.state" :tone="look.tone" :line="look.line" />
  </div>
  <div
    v-if="isKey"
    class="keystatus statusfold statushead statusflat"
    :class="{ 'field-room': !refused }"
    :inert="!refused || undefined"
    :aria-hidden="!refused || undefined"
  >
    <StatusLine :state="t('settings.tnc.state.waiting')" tone="tnc-waiting" :line="t('layers.aisstream.refused')" />
  </div>
</template>
