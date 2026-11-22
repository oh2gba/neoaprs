<script setup lang="ts">
// The button of the Detailed map row of the Map group in Settings (ActionRow.vue): **Download
// map**. The first press runs the estimate; then it asks "Download 493 MB?" and the second press
// downloads. Progress and results are under the row (MapFetchNotes.vue). A setting still being
// saved (`stale`) disables it, unless the form saves first (`early`, the setup guide). A radius
// change takes the question back.
import { computed, ref, watch } from "vue";
import { t } from "@/i18n";
import { useSure } from "@/composables/useSure";
import { bytesText } from "@/lib/format";
import { blockedText, currentEstimate, isRunning } from "@/lib/mapfetch";
import type { Command, MapState } from "@/protocol/protocol";

const props = defineProps<{
  map: MapState;
  stale: boolean;
  send: (command: Command) => boolean;
  early?: boolean;
  id?: string;
}>();

const running = computed(() => isRunning(props.map));
const estimate = computed(() => currentEstimate(props.map));
const idle = computed(() => !running.value && !props.stale && (props.early || props.map.blocked === ""));
const why = computed(() =>
  props.stale
    ? props.early
      ? undefined
      : t("settings.saving")
    : running.value || props.early
      ? undefined
      : blockedText(props.map) || undefined,
);
/** The first press was made and the size is not known yet. */
const checking = ref(false);
/** The size is known and the button asks "Download 493 MB?"; the second press downloads. It asks
 * until answered or taken back. */
const sure = useSure<"download">(null);
const asking = computed(() => sure.armed.value !== null);
const reset = (): void => {
  checking.value = false;
  sure.disarm();
};
watch([() => props.map.radius_km, () => props.map.maxzoom], reset);
// A setting that starts saving takes the question back, but not the wait for the size.
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
      ? t("settings.map.download_size", { size: bytesText(estimate.value.bytes) })
      : props.map.state === "downloading"
        ? t("settings.map.downloading")
        : props.map.detail
          ? t("settings.map.download_again")
          : t("settings.map.download"),
);
/** Three digits, reserving the room of "Download 493 MB?" before the estimate is known. */
const ROOM_BYTES = 888_000_000;
/** Every word the button can say, stacked with the unused ones hidden (`.twowords`), so that its
 * width never changes. */
const faces = computed(() => [
  ...new Set([
    t("settings.map.download"),
    t("settings.map.download_again"),
    t("settings.map.checking"),
    t("settings.map.downloading"),
    t("settings.map.download_size", { size: bytesText(ROOM_BYTES) }),
    label.value,
  ]),
]);
</script>

<template>
  <button
    :id="id"
    class="btn mapfetch-button"
    :class="{ danger: asking }"
    type="button"
    :disabled="!idle || checking"
    :title="why"
    @click="press"
  >
    <span class="twowords"
      ><span
        v-for="face in faces"
        :key="face"
        :class="{ 'twowords-off': face !== label }"
        :aria-hidden="face !== label"
        >{{ face }}</span
      ></span
    >
  </button>
  <button v-if="running" class="btn" type="button" @click="send({ cmd: 'map_cancel' })">
    {{ t("settings.map.cancel") }}
  </button>
</template>
