<script setup lang="ts">
// The Radio group of the Settings tab: the RX only tickbox first (ticked is `station/transmit` false), then a box for each radio of the station that is not removed, in the daemon's order (RadioBox: its Enable, its Name
// and Remove while the station has several radios, its status line and behind the arrow its type, its fields and what its type can do), then, while more than one radio is on, the main radio (MainRadio), and Add radio
// last (RadioAdd). The main radio stands after the last box, so that its coming and going as a radio is ticked or unticked moves nothing above it, the tickbox just clicked least of all; a station with one radio on sees
// no main radio (plan section 6, decision 4). The Names are there for every box while the station has several radios, not only once a second radio is on, so that ticking a radio moves nothing under the pointer and a
// radio that is off can be renamed and removed (plan section 6). A station with one radio has its one box as it always had. The Enable of the only radio that is on is greyed, since a station keeps one on: a radio's
// tick counts at once, before the daemon tells it back. The sound cards and the ports are asked for again when the HF radio of before is ticked, and for a radio whose type has a sound card when it is ticked (the daemon
// lists the sound cards only for a radio that is on); the page leads to the box of a radio this group's Add radio has just added once its row comes (lib/attention.ts: the box opens, comes into view and its Enable takes the keyboard),
// and not to one that another place added (the setup guide's Radio step, which is this group with `guide`: no RX only, no main radio, no Tune, level or scope, and the ids of its place).
import { computed, reactive, ref, watch } from "vue";
import MainRadio from "@/components/MainRadio.vue";
import RadioAdd from "@/components/RadioAdd.vue";
import RadioBox from "@/components/RadioBox.vue";
import SettingsSwitch from "@/components/SettingsSwitch.vue";
import { useRadios } from "@/composables/useRadios";
import type { Settings } from "@/composables/useSettings";
import { useDaemonContext } from "@/composables/useDaemonContext";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { attend } from "@/lib/attention";
import { hfOn } from "@/lib/radiosides";
import { RX_ONLY_KEY } from "@/lib/settings";
import { boxIds, enableId, flatOf, onInForm } from "@/lib/settingsradio";
import type { PageRadio } from "@/lib/radios";

const props = withDefaults(
  defineProps<{
    keys: readonly string[];
    settings: Settings;
    form: SettingsFormState;
    defaults: Record<string, string>;
    /** the setup guide's Radio step: the boxes and Add radio alone (plan section 6: "Left out of the guide: RX only, the main radio, Tune, the level and the scope") */
    guide?: boolean;
  }>(),
  { guide: false },
);
const { send, lastError } = useDaemonContext();
const ids = boxIds();
const radios = useRadios();

/** The ticks of the radios other than those of before that the daemon has not told back yet (RadioBox's `pending`). */
const ticks = reactive(new Map<number, boolean>());
/** Whether a radio is on as the form holds it: a radio of before by its setting as it is being changed, any other by its tick on its way, else as the daemon told it. */
const on = (radio: PageRadio): boolean => ticks.get(radio.id) ?? onInForm(radio, props.settings.values.value, props.settings.draft);
const boxes = computed(() => radios.all.value.filter((radio) => !radio.removed));
const several = computed(() => boxes.value.length > 1);
const onCount = computed(() => boxes.value.filter(on).length);
function pending(radio: PageRadio, enabled: boolean | null): void {
  if (enabled === null) ticks.delete(radio.id);
  else ticks.set(radio.id, enabled);
}
watch(
  () => hfOn(props.settings.draft),
  (wanted) => wanted && send({ cmd: "list_ports" }),
);
// a radio other than those of before whose type has a sound card: its list when it is ticked
watch(
  () => boxes.value.filter((radio) => flatOf(radio, props.settings.values.value) === null && radio.enabled && radio.row.can.tune).map((radio) => radio.id),
  (now, before) => {
    for (const id of now) if (!(before ?? []).includes(id)) send({ cmd: "list_ports", radio: id });
  },
);
// the radio this group's Add radio added: once, when its row comes (a refusal of the add ends the wait)
const adding = ref(false);
watch(
  () => radios.added.value,
  (radio, before) => {
    if (radio === null || radio.id === before?.id || !adding.value) return;
    adding.value = false;
    void attend(ids(enableId(radio, props.settings.values.value)));
  },
);
watch(lastError, (toast) => {
  if (toast?.cmd === "radio_add") adding.value = false;
});
</script>

<template>
  <SettingsSwitch v-if="!guide && keys.includes(RX_ONLY_KEY)" :name="RX_ONLY_KEY" :settings="settings" :form="form" :defaults="defaults" />
  <RadioBox
    v-for="radio in boxes"
    :key="radio.id"
    :radio="radio"
    :keys="keys"
    :settings="settings"
    :form="form"
    :defaults="defaults"
    :named="several"
    :only="on(radio) && onCount === 1"
    :tools="!guide"
    @pending="pending(radio, $event)"
  />
  <MainRadio v-if="!guide && onCount > 1" :settings="settings" :form="form" />
  <RadioAdd :id="ids('set-radio-add')" @added="adding = true" />
</template>
