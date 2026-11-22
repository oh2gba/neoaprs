<script setup lang="ts">
// The Radio group of the Settings tab: a RadioBox per radio that is not removed in the daemon's
// order, and Add radio last. Names are shown for every box while the
// station has several radios, so that ticking a radio moves nothing. The Enable of the only radio
// that is on is greyed. A radio's tick counts at once, before the daemon confirms. Sound cards and
// ports are asked again when a radio whose type has a sound card is ticked. The page leads to the
// box of a radio added here, not to one added elsewhere. With `guide` it is the setup guide's Radio
// step: no Tune, level or scope, and the ids of its place.
import { computed, reactive, ref, watch } from "vue";
import RadioAdd from "@/components/RadioAdd.vue";
import RadioBox from "@/components/RadioBox.vue";
import { useRadios } from "@/composables/useRadios";
import type { Settings } from "@/composables/useSettings";
import { useDaemonContext } from "@/composables/useDaemonContext";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { attend } from "@/lib/attention";
import { boxIds, enableId } from "@/lib/settingsradio";
import type { PageRadio } from "@/lib/radios";

withDefaults(
  defineProps<{
    settings: Settings;
    form: SettingsFormState;
    defaults: Record<string, string>;
    /** the setup guide's Radio step: the boxes and Add radio alone */
    guide?: boolean;
  }>(),
  { guide: false },
);
const { send, lastError } = useDaemonContext();
const ids = boxIds();
const radios = useRadios();

/** The ticks of the radios the daemon has not confirmed yet (RadioBox's `pending`). */
const ticks = reactive(new Map<number, boolean>());
/** Whether a radio is on as the form holds it: the pending tick, else the daemon's value. */
const on = (radio: PageRadio): boolean => ticks.get(radio.id) ?? radio.enabled;
const boxes = computed(() => radios.all.value.filter((radio) => !radio.removed));
const several = computed(() => boxes.value.length > 1);
const onCount = computed(() => boxes.value.filter(on).length);
function pending(radio: PageRadio, enabled: boolean | null): void {
  if (enabled === null) ticks.delete(radio.id);
  else ticks.set(radio.id, enabled);
}
// a radio whose type has a sound card: ask for its list when it is ticked
watch(
  () => boxes.value.filter((radio) => radio.enabled && radio.row.can.tune).map((radio) => radio.id),
  (now, before) => {
    for (const id of now) if (!(before ?? []).includes(id)) send({ cmd: "list_ports", radio: id });
  },
);
// the radio this group's Add radio added: lead to it once, when its row comes (a refusal ends the
// wait)
const adding = ref(false);
watch(
  () => radios.added.value,
  (radio, before) => {
    if (radio === null || radio.id === before?.id || !adding.value) return;
    adding.value = false;
    void attend(ids(enableId(radio)));
  },
);
watch(lastError, (toast) => {
  if (toast?.cmd === "radio_add") adding.value = false;
});
</script>

<template>
  <RadioBox
    v-for="radio in boxes"
    :key="radio.id"
    :radio="radio"
    :settings="settings"
    :form="form"
    :defaults="defaults"
    :named="several"
    :only="on(radio) && onCount === 1"
    :tools="!guide"
    @pending="pending(radio, $event)"
  />
  <RadioAdd :id="ids('set-radio-add')" @added="adding = true" />
</template>
