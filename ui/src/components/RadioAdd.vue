<script setup lang="ts">
// Add radio, the last row of the Radio group (and of the setup guide's Radio step): a choice of the type of the new radio, from the one list of every type in groups (FM, HF, LoRa, Without a radio: lib/settingsradio.ts;
// the radio's kind follows its type and stays), with the Add button
// beside it, as a button that belongs to a field stands beside it. Choosing a type adds nothing: a type looked at with the arrow keys of a closed list is chosen too. Add adds the radio (`radio_add`, with no name: the
// daemon calls it by its kind and its number, "FM 2"), and the choice is ready for the next; the new radio's box comes with its row (SettingsRadio.vue leads to it). Add is greyed while no type is chosen. The (i) is the
// Radio type's, of the one list. A refusal is the daemon's, in the toast.
import { computed, ref } from "vue";
import SettingsField from "@/components/SettingsField.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { t } from "@/i18n";
import type { FieldInfo } from "@/lib/settings";
import { addTypeChoices } from "@/lib/settingsradio";

const props = withDefaults(defineProps<{ id?: string }>(), { id: "set-radio-add" });
const emit = defineEmits<{ added: [type: string] }>();
const { send, status } = useDaemonContext();
const chosen = ref("");
const info = computed<FieldInfo>(() => ({
  label: t("radio.add"),
  kind: "choice",
  choices: [{ value: "", label: t("settings.profile.label") }, ...addTypeChoices(status.value?.unavailable_types)],
  tipLabel: t("settings.profile.tip_label"),
  tip: [t("settings.profile.tip1"), t("settings.profile.tip2")],
}));

function add(): void {
  const type = chosen.value;
  if (type === "") return;
  send({ cmd: "radio_add", type });
  chosen.value = "";
  emit("added", type);
}
</script>

<template>
  <SettingsField
    :id="props.id"
    class="radioadd"
    :info="info"
    :model-value="chosen"
    fallback=""
    error=""
    :changed="false"
    :apply="true"
    @choose="chosen = $event"
  >
    <template #after>
      <button :id="`${props.id}-button`" class="btn" type="button" :disabled="chosen === ''" @click="add">{{ t("radio.add_button") }}</button>
    </template>
  </SettingsField>
</template>
