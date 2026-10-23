<script setup lang="ts">
// What the daemon knows of one station, as a card over the map, in the few facts a person asks for: the symbol with its name and a green check mark beside the call for a station that was heard direct (no repeater), when it was last heard ("6 min ago", the full time when the mouse rests on it), the position and how far and in which direction it is from us, how fast it moves (only a station that does),
// the altitude, the status and the comment, and one line of how its packets reach us ("Reached us via OH2RCH-2", or "direct"). A row with nothing to say is left out. The rest is under "Details", closed (components/StationDetails.vue: the path as it was sent, the counts of the routes, the best route, when it was first heard, the packets, the decoded extras).
// A weather station (the weather symbol, or one that has sent weather) has its weather panel at the top (components/WeatherPanel.vue). "Message" opens the Messages tab with the station as the addressee, where the path its messages go by and RF only are set; the timeout field, under Details, is how long it stays on the map.
// With several cards open (Ctrl+click, components/StationCards.vue) each is `compact`: the head, the weather readings without the graphs, or the few facts that matter, and "More", which makes it the only card, whole. "Forget" takes it out of the station book (it is back when it is heard again); it asks twice, and forgets the first click after 5 s like the other buttons that ask twice (`useSure`). An object or an item of ours has "Edit" (the Objects tab opens with it) and "Kill" (it asks twice, too) in place of "Message" and "Forget", and none of the fields of a station that is heard.
import { computed, watch } from "vue";
import IconButton from "@/components/IconButton.vue";
import DirectMark from "@/components/DirectMark.vue";
import RouteText from "@/components/RouteText.vue";
import StationDetails from "@/components/StationDetails.vue";
import StationTimeout from "@/components/StationTimeout.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import WeatherPanel from "@/components/WeatherPanel.vue";
import { useSure } from "@/composables/useSure";
import { timedOut, type Aging } from "@/lib/aging";
import { qrzUrl } from "@/lib/calls";
import { heardDirect, reachedText } from "@/lib/routes";
import { agoWords, altitudeText, bearingText, dateTimeText, distanceText, positionText, speedText } from "@/lib/format";
import { isWeatherStation } from "@/lib/weather";
import type { StationRow, WeatherSeriesMessage } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{
    row: StationRow;
    now: number;
    aging?: Aging;
    weatherSeries?: WeatherSeriesMessage | null;
    /** One of several cards: the short version. */
    compact?: boolean;
  }>(),
  {
    aging: () => ({ timeouts: new Map<string, number>(), defaultMin: 0 }),
    weatherSeries: null,
    compact: false,
  },
);
const emit = defineEmits<{
  forget: [call: string];
  edit: [name: string];
  kill: [name: string];
  message: [call: string];
  timeout: [call: string, minutes: number];
  clearTimeout: [call: string];
  weather: [call: string, hours: number];
  close: [];
  only: [call: string];
}>();

const sure = useSure<string>();
watch(() => props.row.call, sure.disarm);

const armed = computed(() => sure.armed.value === props.row.call);
const forget = (): void => sure.press(props.row.call, () => emit("forget", props.row.call));
const kill = (): void => sure.press(props.row.call, () => emit("kill", props.row.call));

const qrz = computed(() => (props.row.kind === "station" ? qrzUrl(props.row.call) : null));
const fromUs = computed(() => (props.row.distance_km === null ? null : `${distanceText(props.row.distance_km)} km, ${bearingText(props.row.bearing_deg)}`));
const position = computed(() => (props.row.lat === null || props.row.lon === null ? null : positionText(props.row.lat, props.row.lon)));
/** Only a station that moves has a speed and a course worth saying: "85 km/h, course 96° E". */
const moving = computed(() => {
  const { speed_kmh: speed, course_deg: course } = props.row;
  if (speed === null || speed <= 0) return null;
  return course === null ? speedText(speed) : `${speedText(speed)}, course ${bearingText(course)}`;
});
const weather = computed(() => isWeatherStation(props.row));
const reached = computed(() => (props.row.kind === "station" && !props.row.is_me && !props.row.own ? reachedText(props.row) : null));
</script>

<template>
  <section class="card" :class="{ compact }" aria-label="Station">
    <header class="card-head">
      <SymbolIcon :table="row.symbol_table" :code="row.symbol_code" :size="compact ? 24 : 32" />
      <div class="card-title">
        <span class="card-call">
          <strong>{{ row.call }}</strong>
          <DirectMark v-if="heardDirect(row)" />
          <a v-if="qrz" class="qrz" :href="qrz" target="_blank" rel="noopener noreferrer" title="Open the QRZ page of this call">QRZ</a>
        </span>
        <span class="muted">{{ row.symbol_name }}{{ row.is_me ? " (our station)" : row.own ? " (ours)" : "" }}</span>
      </div>
      <button v-if="compact" class="btn small card-more" type="button" title="Show all of this card, and close the others" @click="emit('only', row.call)">
        More
      </button>
      <IconButton kind="close" class="card-close" label="Close" @click="emit('close')" />
    </header>
    <div class="card-body">
      <WeatherPanel v-if="weather" :row="row" :series="weatherSeries" :now="now" :compact="compact" @ask="(c, h) => emit('weather', c, h)" />
      <dl v-if="!(compact && weather)" class="card-fields">
        <template v-if="row.kind !== 'station'">
          <dt>Kind</dt>
          <dd>{{ row.kind }}, reported by {{ row.reported_by || "-" }}</dd>
        </template>
        <dt>Last heard</dt>
        <dd :title="dateTimeText(row.last_heard)">{{ agoWords(row.last_heard, now) }}</dd>
        <template v-if="position !== null && !compact">
          <dt>Position</dt>
          <dd>{{ position }}<span v-if="timedOut(aging, row, now)" class="timedword"> - timed out</span></dd>
        </template>
        <template v-if="fromUs !== null">
          <dt>From us</dt>
          <dd>{{ fromUs }}</dd>
        </template>
        <template v-if="moving !== null">
          <dt>Speed</dt>
          <dd>{{ moving }}</dd>
        </template>
        <template v-if="row.altitude_m !== null && !compact">
          <dt>Altitude</dt>
          <dd>{{ altitudeText(row.altitude_m) }}</dd>
        </template>
        <template v-if="row.last_status">
          <dt>Status</dt>
          <dd>{{ row.last_status }}</dd>
        </template>
        <template v-if="row.last_comment">
          <dt>Comment</dt>
          <dd>{{ row.last_comment }}</dd>
        </template>
        <template v-if="reached !== null && !compact">
          <dt>Reached us</dt>
          <dd><RouteText :text="reached" /></dd>
        </template>
      </dl>
      <StationDetails v-if="!compact" :row="row">
        <div v-if="!row.is_me && !row.own" class="card-path">
          <StationTimeout :call="row.call" :aging="aging" @set="(c, m) => emit('timeout', c, m)" @clear="emit('clearTimeout', $event)" />
        </div>
      </StationDetails>
    </div>
    <footer v-if="row.own && !compact" class="card-foot">
      <button class="btn primary" type="button" @click="emit('edit', row.call)">Edit</button>
      <button class="btn forget" :class="{ danger: armed }" type="button" @click="kill">{{ armed ? "Really kill?" : "Kill" }}</button>
    </footer>
    <footer v-else-if="!row.is_me && !compact" class="card-foot">
      <button v-if="row.kind === 'station'" class="btn primary" type="button" @click="emit('message', row.call)">Message</button>
      <button class="btn forget" :class="{ danger: armed }" type="button" @click="forget">{{ armed ? "Really forget?" : "Forget" }}</button>
    </footer>
  </section>
</template>
