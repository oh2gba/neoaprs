<script setup lang="ts">
// The suggested frequencies in an HF radio's box: one row whose button opens them in a dialog
// (ExplainDialog), one line that says what they are and the list (`modem.frequencies`: the
// project's list, else the version page's dial, else the built-in five), the band and the dial on
// a line each, with the room of five lines kept so that the dialog does not change size when the
// list comes. The daemon is asked to refresh the list (`frequencies`; at most every fifteen
// minutes) when the row comes into view, for the PSK Reporter dial's choice, and when the dialog
// opens; an ask before the socket opened is made when it opens.
import { computed, ref, watch } from "vue";
import ExplainDialog from "@/components/ExplainDialog.vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useWhenShown } from "@/composables/useWhenShown";
import { t } from "@/i18n";
import type { PageRadio } from "@/lib/radios";
import { boxIds } from "@/lib/settingsradio";

const props = defineProps<{ radio: PageRadio }>();
const { send, connection } = useDaemonContext();
const row = ref<HTMLElement | null>(null);
const button = ref<HTMLButtonElement | null>(null);
const open = ref(false);
const lines = computed(() => props.radio.row.modem?.frequencies ?? []);
const ids = boxIds();
/** The id of the row's button, with the radio's id, for the Settings tab or the setup guide. */
const buttonId = computed(() => ids(`hf-frequencies-${props.radio.id}`));
let missed = false; // asked before the socket opened
const ask = (): void => void (connection.value === "open" ? send({ cmd: "frequencies" }) : (missed = true));
useWhenShown(row, ask);
watch(connection, (now) => {
  if (now !== "open" || !missed) return;
  missed = false;
  send({ cmd: "frequencies" });
});
function show(): void {
  open.value = true;
  ask();
}
</script>

<template>
  <div ref="row" class="field">
    <label :for="buttonId">{{ t("settings.hf_frequencies.label") }}</label>
    <div class="field-control">
      <button :id="buttonId" ref="button" type="button" class="btn" @click="show">
        {{ t("settings.hf_frequencies.show") }}
      </button>
    </div>
  </div>
  <Teleport v-if="open" to="body">
    <ExplainDialog :title="t('settings.hf_frequencies.label')" :opener="button" @close="open = false">
      <p>{{ t("settings.hf_frequencies.what") }}</p>
      <ul class="freqs">
        <li v-for="f in lines" :key="f.band" class="freq">
          <span class="band">{{ f.band }}</span> <span class="dial mono">{{ f.dial }}</span>
        </li>
      </ul>
    </ExplainDialog>
  </Teleport>
</template>

<style scoped>
.freqs {
  min-height: 7.5em;
  margin: 0;
  padding: 0;
  line-height: 1.5;
  list-style: none;
}
.freq {
  height: 1.5em; /* one line exactly, whatever the fonts' heights */
  white-space: nowrap;
}
.band {
  display: inline-block;
  min-width: 4.5ch;
  color: var(--muted);
}
</style>
