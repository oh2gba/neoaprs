<script setup lang="ts">
// The card of a ship or an aircraft that was clicked on the map (composables/useTrafficMap.ts): its name in full in the head, the facts the feed gives (lib/traffic.ts: for a ship the type, MMSI, call sign, IMO, status, speed,
// course, heading, size, draught, destination and ETA; for an aircraft the type, flight, registration, altitude, speed, track and squawk) and a quiet line that it was received over the internet and never sent. At the top right of
// the map, clear of the station cards at the left and the statistics card at the bottom; its cross closes it, and it goes by itself when the ship or the aircraft leaves the feed.
import { computed } from "vue";
import IconButton from "@/components/IconButton.vue";
import { t } from "@/i18n";
import { aircraftFacts, shipFacts, trafficTitle, type TrafficPick } from "@/lib/traffic";
import type { AircraftRow, ShipRow } from "@/protocol/protocol";

const props = defineProps<{ pick: TrafficPick; ship?: ShipRow; aircraft?: AircraftRow; now: number }>();
const emit = defineEmits<{ close: [] }>();
const title = computed(() => trafficTitle(props.pick, props.ship, props.aircraft));
const facts = computed(() => (props.ship ? shipFacts(props.ship, props.now) : props.aircraft ? aircraftFacts(props.aircraft, props.now) : []));
</script>

<template>
  <section class="card trafficcard" :aria-label="title">
    <header class="card-head">
      <div class="card-title">
        <span class="card-call"
          ><strong>{{ title }}</strong></span
        >
      </div>
      <IconButton kind="close" class="card-close" :label="t('traffic.card.close')" @click="emit('close')" />
    </header>
    <div class="card-body">
      <dl class="card-fields">
        <template v-for="fact in facts" :key="fact.label">
          <dt>{{ fact.label }}</dt>
          <dd>{{ fact.value }}</dd>
        </template>
      </dl>
      <p class="traffic-received">{{ t("traffic.card.received") }}</p>
    </div>
  </section>
</template>
