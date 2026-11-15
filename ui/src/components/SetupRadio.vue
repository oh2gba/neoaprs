<script setup lang="ts">
// Step 4 of the first-run guide, live as the Radio group of the Settings tab is (plan section 6): the same group (SettingsRadio with `guide`), a box for each radio of the station that is not removed (RadioBox: its Enable, its Name and
// Remove while the station has several radios, its status line and behind the arrow its type, the type's fields, the frequencies, Find my radio and the Terminal), and Add radio under them. A change applies at once, as in the
// Settings tab (the same settings, the same queue and Undo), so a radio made or changed here stays when the guide is closed. Left out: RX only, the main radio, Tune, the transmit level and the scope.
// A station with no radio (a fresh installation) has one box, the radio it is adding: Add radio, the type from the whole list and its Add; once the new radio's row has come its box takes the place of this one, with the
// type's fields and its status line at once, and Add radio under it. Before the daemon has told its settings and its radios the step has nothing (before the topic `radios` the radios would be those of the settings of
// before, two boxes where the station may have one). The ids are the guide's own (`setup-fm-enabled`,
// lib/settingsradio.ts BOX_IDS): every tab stays mounted, so the Settings tab's boxes are on the page too.
import { computed, provide, ref, watch } from "vue";
import RadioAdd from "@/components/RadioAdd.vue";
import SettingsBox from "@/components/SettingsBox.vue";
import SettingsRadio from "@/components/SettingsRadio.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { useSettingsForm } from "@/composables/useSettingsForm";
import { t } from "@/i18n";
import { attend } from "@/lib/attention";
import { radioStepKeys } from "@/lib/setup";
import { BOX_IDS, placedId, radioElementId } from "@/lib/settingsradio";

const PLACE = "setup";
provide(BOX_IDS, PLACE);
const { config, settings, lastError } = useDaemonContext();
const form = useSettingsForm(config, settings, "settings");
const { defaults } = form;
const radios = useRadios();
const keys = computed(() => radioStepKeys(settings.values.value, settings.draft));
/** The station has no radio (none, or every one removed): the step is the box of the radio it is adding. */
const none = computed(() => radios.all.value.every((radio) => radio.removed));

// the first radio, added from that box: the page leads to its box once its row has come, to its type (its Enable is greyed: it is the only radio), and a refusal of the add ends the wait (the group's own Add radio leads to
// the radios it adds)
const adding = ref(false);
watch(
  () => radios.added.value,
  (radio) => {
    if (radio === null || !adding.value) return;
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
    <SettingsRadio v-else guide :keys="keys" :settings="settings" :form="form" :defaults="defaults" />
  </template>
</template>
