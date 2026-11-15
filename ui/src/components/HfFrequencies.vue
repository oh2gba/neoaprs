<script setup lang="ts">
// The suggested frequencies in the HF radio's box: the project's list (the daemon says it in `hf.modem.frequencies`, from a small file on the project's server, else the version page's dial, else the built-in two), one line for each, the band and the dial in
// the monospace font, as plain text to read: not an input box, and the label says "suggested", since nothing here is read from the radio. The room of four lines (the most the list has: MAX_FREQUENCIES) is kept, so that nothing moves when the list changes length. When the row comes into view (the
// tab opened, the fold unfolded) the daemon is asked to look at the project's file again (`frequencies`), which it does at most every fifteen minutes; a row that came into view before the socket was open asks when it opens,
// as the HF tests tab does. In the box of a radio other than the HF radio of before (`radio`) the list is its modem's; the list is the station's either way.
import { computed, ref, watch } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useWhenShown } from "@/composables/useWhenShown";
import { t } from "@/i18n";
import { HF_ID } from "@/lib/radiosides";
import type { PageRadio } from "@/lib/radios";
import { boxIds } from "@/lib/settingsradio";

const props = withDefaults(defineProps<{ radio?: PageRadio | null }>(), { radio: null });
const { hf, send, connection } = useDaemonContext();
const row = ref<HTMLElement | null>(null);
const own = computed(() => props.radio !== null && props.radio.id !== HF_ID);
const lines = computed(() => (own.value ? props.radio?.row.modem?.frequencies : hf.value?.modem?.frequencies) ?? []);
const ids = boxIds();
/** The id of the row's output: the HF radio of before's as it was, another radio's with its id, in the ids of the place (the Settings tab's, or the setup guide's). */
const outputId = computed(() => ids(own.value ? `hf-frequencies-${props.radio?.id ?? ""}` : "hf-frequencies"));
let missed = false; // the row came into view before the socket was open: it is asked when the socket opens
useWhenShown(row, () => void (connection.value === "open" ? send({ cmd: "frequencies" }) : (missed = true)));
watch(connection, (now) => {
  if (now !== "open" || !missed) return;
  missed = false;
  send({ cmd: "frequencies" });
});
</script>

<template>
  <div ref="row" class="field">
    <label :for="outputId">{{ t("settings.hf_frequencies.label") }}</label>
    <div class="field-control">
      <output :id="outputId" class="freqs"
        ><span v-for="f in lines" :key="f.band" class="freq"
          ><span class="band">{{ f.band }}</span> <span class="dial mono">{{ f.dial }}</span></span
        ></output
      >
    </div>
  </div>
</template>

<style scoped>
.freqs {
  display: block;
  min-height: 6em;
  line-height: 1.5;
}
.freq {
  display: block;
}
.band {
  display: inline-block;
  min-width: 3.5ch;
  color: var(--muted);
}
</style>
