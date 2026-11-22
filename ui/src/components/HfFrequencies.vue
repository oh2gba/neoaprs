<script setup lang="ts">
// The suggested frequencies in an HF radio's box (`modem.frequencies`: the project's list, else
// the version page's dial, else the built-in four), one plain-text line each. Room for four
// lines (MAX_FREQUENCIES) is kept so that nothing moves. When the row comes into view the daemon
// is asked to refresh the list (`frequencies`; at most every fifteen minutes); a row that
// appeared before the socket opened asks when it opens.
import { computed, ref, watch } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useWhenShown } from "@/composables/useWhenShown";
import { t } from "@/i18n";
import type { PageRadio } from "@/lib/radios";
import { boxIds } from "@/lib/settingsradio";

const props = defineProps<{ radio: PageRadio }>();
const { send, connection } = useDaemonContext();
const row = ref<HTMLElement | null>(null);
const lines = computed(() => props.radio.row.modem?.frequencies ?? []);
const ids = boxIds();
/** The id of the row's output, with the radio's id, for the Settings tab or the setup guide. */
const outputId = computed(() => ids(`hf-frequencies-${props.radio.id}`));
let missed = false; // came into view before the socket opened
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
  height: 1.5em; /* one line exactly, whatever the fonts' heights */
  white-space: nowrap;
}
.band {
  display: inline-block;
  min-width: 3.5ch;
  color: var(--muted);
}
</style>
