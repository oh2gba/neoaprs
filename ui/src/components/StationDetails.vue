<script setup lang="ts">
// The rest of a station's card, closed until "Details" is opened: how its packets reach us (the path of the latest one as it was sent, how many came direct and by which repeaters, the best route and the path to send by),
// when it was first heard, the number of packets, and what the daemon decodes beyond the position, a line each: the data extensions (PHG, range, DF, area), the Maidenhead locator of its status, and the telemetry channels with the names and units it defined.
// A row with nothing to say is left out. It is for the few who want to know; the card says the main facts (components/StationCard.vue).
import { computed } from "vue";
import { extensionRows, locatorText, telemetryBitsText, telemetryText } from "@/lib/details";
import { dateTimeText, pathText } from "@/lib/format";
import { bestText, heardText } from "@/lib/routes";
import type { StationRow } from "@/protocol/protocol";

const props = defineProps<{ row: StationRow }>();

const extensions = computed(() => extensionRows(props.row.extensions));
const heard = computed(() => heardText(props.row));
const best = computed(() => bestText(props.row));
</script>

<template>
  <details class="more card-details">
    <summary>Details</summary>
    <dl class="card-fields">
      <template v-for="ext in extensions" :key="ext.label">
        <dt>{{ ext.label }}</dt>
        <dd>{{ ext.text }}</dd>
      </template>
      <template v-if="row.locator !== null">
        <dt>Locator</dt>
        <dd>{{ locatorText(row.locator) }}</dd>
      </template>
      <template v-if="row.telemetry !== null">
        <dt>Telemetry</dt>
        <dd :title="dateTimeText(row.telemetry_at)">{{ telemetryText(row.telemetry) }}</dd>
        <dt>Bits</dt>
        <dd>{{ telemetryBitsText(row.telemetry) }}</dd>
      </template>
      <dt>First heard</dt>
      <dd>{{ dateTimeText(row.first_heard) }}</dd>
      <template v-if="row.last_path.length > 0">
        <dt>Path</dt>
        <dd class="mono">{{ pathText(row.last_path) }}</dd>
      </template>
      <template v-if="heard !== '-'">
        <dt>Heard</dt>
        <dd>{{ heard }}</dd>
      </template>
      <template v-if="best !== '-'">
        <dt>Best route</dt>
        <dd>{{ best }}</dd>
      </template>
      <dt>Packets</dt>
      <dd>{{ row.packets }}</dd>
    </dl>
  </details>
</template>
