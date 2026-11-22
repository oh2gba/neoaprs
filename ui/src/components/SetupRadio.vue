<script setup lang="ts">
// Step 4 of the first-run guide, live like the Radio group: the same group (SettingsRadio with
// `guide`) with a RadioBox per radio and Add radio under them. A change applies at once, with the
// same settings, queue and Undo as the Settings tab. Left out: Tune, the transmit level and the
// scope. A station with no radio has one box for the radio being added; when its row
// arrives the box is replaced by the radio's own. Before the daemon has listed settings and radios
// the step is empty. The ids are the guide's own (lib/settingsradio.ts BOX_IDS); the Settings tab's
// boxes are in the page too.
import { computed, provide, ref, watch } from "vue";
import RadioAdd from "@/components/RadioAdd.vue";
import SettingsBox from "@/components/SettingsBox.vue";
import SettingsRadio from "@/components/SettingsRadio.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { useSettingsForm } from "@/composables/useSettingsForm";
import { t } from "@/i18n";
import { attend } from "@/lib/attention";
import { BOX_IDS, placedId, radioElementId } from "@/lib/settingsradio";

const PLACE = "setup";
provide(BOX_IDS, PLACE);
const { config, settings, lastError } = useDaemonContext();
const form = useSettingsForm(config, settings, "settings");
const { defaults } = form;
const radios = useRadios();
/**
 * The station has no radio (none, or all removed): the step is the box of the radio being added.
 */
const none = computed(() => radios.all.value.every((radio) => radio.removed));

// the first radio, added from that box: lead to its box once its row has come, to its type (its
// Enable is greyed as the only radio); a refusal of the add ends the wait
const adding = ref(false);
watch(
  () => radios.added.value,
  (radio, before) => {
    if (radio === null || radio.id === before?.id || !adding.value) return;
    adding.value = false;
    void attend(placedId(PLACE, radioElementId(radio, "type")));
  },
);
watch(lastError, (toast) => {
  if (toast?.cmd === "radio_add") adding.value = false;
});
</script>

<template>
  <template v-if="config && radios.told.value">
    <SettingsBox v-if="none" :title="t('radio.new')">
      <RadioAdd :id="placedId(PLACE, 'set-radio-add')" @added="adding = true" />
    </SettingsBox>
    <SettingsRadio v-else guide :settings="settings" :form="form" :defaults="defaults" />
  </template>
</template>
