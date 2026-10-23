<script setup lang="ts">
// The top of the Beacon tab: what our beacon and our status are doing and, beside each, the button that sends it now ("Beacon now", "Send status now"; the second only while there is a status). A button asks twice
// (what goes on the air cannot be taken back: the first press says "Really send?"), is disabled while the TNC is not connected or while the settings below hold changes that are not saved (what is sent is
// what is saved), and forgets the first press after a few seconds.
import { computed, watch } from "vue";
import { useSure } from "@/composables/useSure";
import { NONE, agoText, dateTimeText, untilText } from "@/lib/format";
import type { StatusMessage } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{ status: StatusMessage | null; connected: boolean; now: number; statusOn?: boolean; unsaved?: boolean; picking?: boolean }>(),
  {
    statusOn: false,
    unsaved: false,
    picking: false,
  },
);
const emit = defineEmits<{ send: []; "send-status": []; arm: [] }>();

const sure = useSure<"beacon" | "status">();
const ready = computed(() => props.connected && !props.unsaved);
const why = computed(() => (props.unsaved ? "Save your changes first" : undefined));

watch(ready, (now) => {
  if (!now) sure.disarm();
});
// picking a place on the map and a send that waits for its second press do not go together: starting one ends the other
watch(
  () => props.picking,
  (now) => {
    if (now) sure.disarm();
  },
);

function press(key: "beacon" | "status", act: () => void): void {
  if (sure.armed.value !== key && props.picking) emit("arm");
  sure.press(key, act);
}

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
    <div class="beaconact">
      <dl class="card-fields">
        <dt>Beacon</dt>
        <dd>{{ interval }}</dd>
        <dt>Last beacon</dt>
        <dd>{{ last }}</dd>
        <dt>Next due</dt>
        <dd>{{ next }}</dd>
      </dl>
      <button
        class="btn primary"
        :class="{ danger: sure.armed.value === 'beacon' }"
        type="button"
        :disabled="!ready"
        :title="why"
        @click="press('beacon', () => emit('send'))"
      >
        {{ sure.armed.value === "beacon" ? "Really send?" : "Beacon now" }}
      </button>
    </div>
    <div v-if="statusOn" class="beaconact">
      <dl class="card-fields">
        <dt>Status</dt>
        <dd>{{ current }}</dd>
      </dl>
      <button
        class="btn primary"
        :class="{ danger: sure.armed.value === 'status' }"
        type="button"
        :disabled="!ready"
        :title="why"
        @click="press('status', () => emit('send-status'))"
      >
        {{ sure.armed.value === "status" ? "Really send?" : "Send status now" }}
      </button>
    </div>
  </section>
</template>
