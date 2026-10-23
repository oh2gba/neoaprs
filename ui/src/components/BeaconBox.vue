<script setup lang="ts">
// Our beacon, under the radio link: how often it is sent, when the last one went out and when the next is due, and "Beacon now", which sends one at once. The button asks twice (a position on the
// air cannot be taken back), is disabled while the TNC is not connected, and forgets the first click after a few seconds.
import { computed, watch } from "vue";
import { useSure } from "@/composables/useSure";
import { NONE, agoText, dateTimeText, untilText } from "@/lib/format";
import type { StatusMessage } from "@/protocol/protocol";

const props = defineProps<{ status: StatusMessage | null; connected: boolean; now: number }>();
const emit = defineEmits<{ send: [] }>();

const sure = useSure<"beacon">();
const armed = computed(() => sure.armed.value === "beacon");

watch(
  () => props.connected,
  (connected) => {
    if (!connected) sure.disarm();
  },
);

const interval = computed(() => {
  const minutes = props.status?.beacon_interval_min;
  return minutes === undefined ? NONE : minutes === 0 ? "off" : `every ${minutes} min`;
});
const last = computed(() => {
  const at = props.status?.beacon_last_sent ?? null;
  return at === null ? NONE : agoText(at, props.now);
});
const current = computed(() => {
  const text = props.status?.station_status ?? "";
  const rig = props.status?.rig_state ?? "unused";
  return `${text === "" ? NONE : text}${rig === "unused" ? "" : ` · rigctld ${rig}`}`;
});
const next = computed(() => {
  const at = props.status?.beacon_next_due ?? null;
  return at === null ? NONE : `${untilText(at, props.now)} (${dateTimeText(at)})`;
});
</script>

<template>
  <section class="beaconbox" aria-label="Beacon">
    <div class="toolbar">
      <strong>Beacon</strong>
      <span class="grow muted">{{ interval }}</span>
      <button class="btn" :class="{ danger: armed }" type="button" :disabled="!connected" @click="sure.press('beacon', () => emit('send'))">
        {{ armed ? "Really send?" : "Beacon now" }}
      </button>
    </div>
    <dl class="card-fields">
      <dt>Last beacon</dt>
      <dd>{{ last }}</dd>
      <dt>Next due</dt>
      <dd>{{ next }}</dd>
      <dt>Status</dt>
      <dd>{{ current }}</dd>
    </dl>
  </section>
</template>
