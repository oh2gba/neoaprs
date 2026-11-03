<script setup lang="ts">
// The Radio group of the Settings tab: the RX only tickbox first (ticked is `station/transmit` false), then the two radios in a box each under their own legend (SettingsBox): the FM radio and the HF radio. A box begins with its Enable tickbox and is that row alone while the radio is unticked.
// Ticked, it has the radio's status line (RadioStatus: the topic `tnc` for FM, `hf` for HF) and behind the arrow its fields: the type of TNC, the port, the speed, or the host and port of a TNC reached over TCP, Find my radio and the terminal for FM; the sound card, the keying and the terminal for HF (SettingsRadioFields).
// The fold is open when the radio is not connected. The Enable of the station's only radio is greyed, since a station has at least one. The sound cards and the ports are asked for again when HF is ticked, since the daemon lists the sound cards only then.
// The HF radio's type (`hf/profile`) is the first of its fields: with the Dummy HF radio chosen the sound card, the keying and Tune are not there, as the FM Dummy has no port; with the Mercury modem the Frequency row (the dial the group agrees on, read-only) and the Tune row stand under the fields where the FM radio has Find my radio; above Tune, only while the program waits for the Windows Firewall, the Fix row.
import { computed, watch } from "vue";
import FindRadioRow from "@/components/FindRadioRow.vue";
import HfFirewallRow from "@/components/HfFirewallRow.vue";
import HfLevelRow from "@/components/HfLevelRow.vue";
import HfScope from "@/components/HfScope.vue";
import HfTuneRow from "@/components/HfTuneRow.vue";
import RadioStatus from "@/components/RadioStatus.vue";
import SettingsBox from "@/components/SettingsBox.vue";
import SettingsRadioFields from "@/components/SettingsRadioFields.vue";
import SettingsSwitch from "@/components/SettingsSwitch.vue";
import type { Settings } from "@/composables/useSettings";
import { useDaemonContext } from "@/composables/useDaemonContext";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { t } from "@/i18n";
import { hfIsMercury } from "@/lib/mercury";
import { firewallFixable } from "@/lib/tncstatus";
import { fmOn, hfOn } from "@/lib/radiosides";
import { RX_ONLY_KEY } from "@/lib/settings";
import type { TncState } from "@/protocol/protocol";

const props = defineProps<{ keys: readonly string[]; settings: Settings; form: SettingsFormState; defaults: Record<string, string> }>();
const { send, tnc, hf, now } = useDaemonContext();

const FM_KEY = "fm/enabled";
const HF_KEY = "hf/enabled";
const HF_PROFILE_KEY = "hf/profile";
const HF_GAIN_KEY = "mercury/tx_gain_db"; // (the Transmit level row's, not a field of the list)
const fm = computed(() => fmOn(props.settings.draft));
const hfRadio = computed(() => hfOn(props.settings.draft));
const mercury = computed(() => hfIsMercury(props.settings.draft));
/** The fields of a radio: the type of the HF radio, the sound card and the keying are the HF radio's (the two of the modem only while it is the modem), the rest the FM radio's; the switches are the boxes' own. */
const fields = (hfBox: boolean) =>
  props.keys.filter(
    (k) =>
      ![RX_ONLY_KEY, FM_KEY, HF_KEY, HF_GAIN_KEY].includes(k) &&
      (k === HF_PROFILE_KEY || k.startsWith("mercury/")) === hfBox &&
      (hfBox && k.startsWith("mercury/") ? mercury.value : true),
  );
const boxes = computed(() => [
  { kind: "fm", legend: t("settings.group.fm_radio"), switch: FM_KEY, radio: tnc.value, on: fm.value, only: fm.value && !hfRadio.value, keys: fields(false) },
  {
    kind: "hf",
    legend: t("settings.group.hf_radio"),
    switch: HF_KEY,
    radio: hf.value,
    on: hfRadio.value,
    only: hfRadio.value && !fm.value,
    keys: fields(true),
  },
]);
/** The fold is open while a radio is not connected: that is when the fields are wanted. */
const unconnected = (radio: TncState | null): boolean => radio !== null && radio.state !== "connected";
watch(hfRadio, (wanted) => wanted && send({ cmd: "list_ports" }));
</script>

<template>
  <SettingsSwitch v-if="keys.includes(RX_ONLY_KEY)" :name="RX_ONLY_KEY" :settings="settings" :form="form" :defaults="defaults" />
  <SettingsBox v-for="box in boxes" :key="box.kind" :title="box.legend">
    <SettingsSwitch v-if="keys.includes(box.switch)" :name="box.switch" :settings="settings" :form="form" :defaults="defaults" :only="box.only" />
    <RadioStatus v-if="box.on" :tnc="box.radio" :now="now" :open="unconnected(box.radio)">
      <SettingsRadioFields :keys="box.keys" :settings="settings" :form="form" :defaults="defaults" />
      <!-- The dial frequency the group agrees on, which the daemon says (`hf.modem.dial`): plain text to read, not a box that looks as if it took typing. -->
      <div v-if="box.kind === 'hf' && mercury && hf?.modem" class="field">
        <label for="hf-frequency">{{ t("settings.hf_frequency.label") }}</label>
        <div class="field-control">
          <output id="hf-frequency" class="dial">{{ hf.modem.dial }}</output>
        </div>
      </div>
      <HfFirewallRow v-if="box.kind === 'hf' && mercury && firewallFixable(hf)" id="hf-firewall" />
      <FindRadioRow v-if="box.kind === 'fm'" id="find-radio" />
      <template v-else-if="mercury">
        <HfTuneRow id="hf-tune" />
        <HfLevelRow v-if="keys.includes(HF_GAIN_KEY)" id="hf-txlevel" :settings="settings" :form="form" />
        <HfScope />
      </template>
    </RadioStatus>
  </SettingsBox>
</template>

<style scoped>
.dial {
  font-weight: 600;
}
</style>
