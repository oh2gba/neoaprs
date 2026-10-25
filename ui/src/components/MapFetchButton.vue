<script setup lang="ts">
// The button at the right end of the Radius row of the Map group (the Settings tab, and the first-run guide's map step), a plain one as the Test button of the Command row is: **Download map**. The first press runs the estimate (a dry run) and says "Checking size…"; when the size is known
// the button asks "Download 493 MB?", and the second press downloads (the world map if it is not there, then the detailed map). Cancel beside it while a job runs; the progress, what a job failed with and the line "Map downloaded 23 Oct" are under the row (components/MapFetchNotes.vue).
// With a detailed map the button says "Download again". The daemon does the work for the radius and the detail it has in force; a setting that is still being saved (`stale`) disables the button for the moment, unless the form saves it before it sends the command (`early`,
// the first-run guide), in which case the daemon having no position yet does not disable it either. A change of the radius takes the question back.
import { computed, ref, watch } from "vue";
import { t } from "@/i18n";
import { useSure } from "@/composables/useSure";
import { currentEstimate, formatBytes, isRunning } from "@/lib/mapfetch";
import type { Command, MapState } from "@/protocol/protocol";

const props = defineProps<{ map: MapState; stale: boolean; send: (command: Command) => boolean; early?: boolean }>();

const running = computed(() => isRunning(props.map));
const estimate = computed(() => currentEstimate(props.map));
const idle = computed(() => !running.value && !props.stale && (props.early || props.map.blocked === ""));
const why = computed(() =>
  props.stale ? (props.early ? undefined : t("settings.saving")) : running.value || props.early ? undefined : props.map.blocked || undefined,
);
/** The first press has been made and the size is not known yet. */
const checking = ref(false);
/** The size is known and the button asks "Download 493 MB?": the second press sends the download (it asks until it is answered or the question is taken back, no time limit). */
const sure = useSure<"download">(null);
const asking = computed(() => sure.armed.value !== null);
const reset = (): void => {
  checking.value = false;
  sure.disarm();
};
watch([() => props.map.radius_km, () => props.map.maxzoom], reset);
// a setting that starts to be saved takes the question back (not the wait for the size: the first-run guide saves its answers as the first press is made)
watch(
  () => props.stale,
  (now) => {
    if (now && asking.value) reset();
  },
);
watch(
  () => props.map.state,
  (state) => {
    if (state === "downloading") reset();
    else if (state === "error") checking.value = false;
  },
);
// the estimate that answers the press
watch(estimate, (now) => {
  if (now && checking.value && !running.value) {
    checking.value = false;
    sure.arm("download");
  }
});
watch(running, (now) => {
  if (!now && checking.value && estimate.value) {
    checking.value = false;
    sure.arm("download");
  }
});

function press(): void {
  if (asking.value && estimate.value) {
    reset();
    props.send({ cmd: "map_fetch" });
  } else {
    checking.value = props.send({ cmd: "map_estimate" });
  }
}
const label = computed(() =>
  checking.value || props.map.state === "estimating"
    ? t("settings.map.checking")
    : asking.value && estimate.value
      ? t("settings.map.download_size", { size: formatBytes(estimate.value.bytes) })
      : props.map.state === "downloading"
        ? t("settings.map.downloading")
        : props.map.detail
          ? t("settings.map.download_again")
          : t("settings.map.download"),
);
</script>

<template>
  <button class="btn mapfetch-button" :class="{ danger: asking }" type="button" :disabled="!idle || checking" :title="why" @click="press">{{ label }}</button>
  <button v-if="running" class="btn" type="button" @click="send({ cmd: 'map_cancel' })">{{ t("settings.map.cancel") }}</button>
</template>
