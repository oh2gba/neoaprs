<script setup lang="ts">
// Add radio, the last row of the Radio group: a choice of type from the list of all types, with an
// Add button beside it. Choosing a type adds nothing; Add sends `radio_add` and the choice is ready
// for the next. A refusal from the daemon appears in the toast.
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
