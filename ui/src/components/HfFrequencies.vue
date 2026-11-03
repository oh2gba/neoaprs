<script setup lang="ts">
// The suggested frequencies in the HF radio's box: the project's list (the daemon says it in `hf.modem.frequencies`, from a small file on the project's server, else the version page's dial, else the built-in two), one line for each, the band and the dial in
// the monospace font, as plain text to read: not an input box, and the label says "suggested", since nothing here is read from the radio. The room of two lines is kept, so that nothing moves when the list changes length. When the row comes into view (the
// tab opened, the fold unfolded) the daemon is asked to look at the project's file again (`hf_frequencies`), which it does at most every fifteen minutes.
import { computed, ref } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useWhenShown } from "@/composables/useWhenShown";
import { t } from "@/i18n";

const { hf, send } = useDaemonContext();
const row = ref<HTMLElement | null>(null);
const lines = computed(() => hf.value?.modem?.frequencies ?? []);
useWhenShown(row, () => send({ cmd: "hf_frequencies" }));
</script>

<template>
  <div ref="row" class="field">
    <label for="hf-frequencies">{{ t("settings.hf_frequencies.label") }}</label>
    <div class="field-control">
      <output id="hf-frequencies" class="freqs"
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
  min-height: 3em;
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
