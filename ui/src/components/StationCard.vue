<script setup lang="ts">
// Everything the daemon knows of one station, as a card over the map: the symbol, the position, how far and in which direction from us, how it moves, when it was heard, the path of its latest
// packet and the route it came by, how its packets reached us (direct, by which repeaters, from the internet), when it was last heard direct and the share of its packets that came direct, and the best route with the path to send by, its status and comment, how many packets it sent. A row with nothing to say
// is left out (no course, speed or altitude for a house, no status when none was heard). "Message" opens the Messages tab with the station as the addressee, where the path its messages go by, RF only and the attempts are set; the timeout field is how long
// it stays on the map. The details that the daemon decodes beyond the position follow the altitude, a line each: the data extensions (PHG, range, DF, area), the Maidenhead locator of its status, and the telemetry channels with the names and units it defined. A weather station (the weather symbol, or one that has sent weather) has its weather panel at the top (components/WeatherPanel.vue). "Forget" takes it out of the station book (it is back when it is heard again); it asks twice, and forgets the first click after 5 s like the other buttons that ask twice (`useSure`). An object or an item of ours has "Edit" (the Objects tab opens with it) and "Kill" (it asks twice, too) in place of "Message" and "Forget", and none of the fields of a station that is heard.
import { computed, watch } from "vue";
import StationTimeout from "@/components/StationTimeout.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import WeatherPanel from "@/components/WeatherPanel.vue";
import { useSure } from "@/composables/useSure";
import { timedOut, type Aging } from "@/lib/aging";
import { qrzUrl } from "@/lib/calls";
import { bestText, directWords, heardText } from "@/lib/routes";
import { extensionRows, locatorText, telemetryBitsText, telemetryText } from "@/lib/details";
import { agoText, altitudeText, bearingText, courseText, dateTimeText, distanceText, pathText, positionText, speedText } from "@/lib/format";
import { isWeatherStation } from "@/lib/weather";
import type { StationRow, WeatherSeriesMessage } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{
    row: StationRow;
    now: number;
    aging?: Aging;
    weatherSeries?: WeatherSeriesMessage | null;
  }>(),
  {
    aging: () => ({ timeouts: new Map<string, number>(), defaultMin: 0 }),
    weatherSeries: null,
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
}>();

const sure = useSure<string>();
watch(() => props.row.call, sure.disarm);

const armed = computed(() => sure.armed.value === props.row.call);
const forget = (): void => sure.press(props.row.call, () => emit("forget", props.row.call));
const kill = (): void => sure.press(props.row.call, () => emit("kill", props.row.call));

const qrz = computed(() => (props.row.kind === "station" ? qrzUrl(props.row.call) : null));
const extensions = computed(() => extensionRows(props.row.extensions));
const fromUs = computed(() => (props.row.distance_km === null ? null : `${distanceText(props.row.distance_km)} km, ${bearingText(props.row.bearing_deg)}`));
const position = computed(() => (props.row.lat === null || props.row.lon === null ? null : positionText(props.row.lat, props.row.lon)));
const heard = computed(() => heardText(props.row));
const best = computed(() => bestText(props.row));
const direct = computed(() => (props.row.kind === "station" && !props.row.is_me ? directWords(props.row, props.now) : null));
</script>

<template>
  <section class="card" aria-label="Station">
    <header class="card-head">
      <SymbolIcon :table="row.symbol_table" :code="row.symbol_code" :size="32" />
      <div class="card-title">
        <span class="card-call">
          <strong>{{ row.call }}</strong>
          <a v-if="qrz" class="qrz" :href="qrz" target="_blank" rel="noopener noreferrer" title="Open the QRZ page of this call">QRZ</a>
        </span>
        <span class="muted">{{ row.symbol_name }}{{ row.is_me ? " (our station)" : row.own ? " (ours)" : "" }}</span>
      </div>
      <button class="iconbtn" type="button" aria-label="Close" title="Close" @click="emit('close')">x</button>
    </header>
    <WeatherPanel v-if="isWeatherStation(row)" :row="row" :series="weatherSeries" :now="now" @ask="(c, h) => emit('weather', c, h)" />
    <dl class="card-fields">
      <template v-if="row.kind !== 'station'">
        <dt>Kind</dt>
        <dd>{{ row.kind }}, reported by {{ row.reported_by || "-" }}</dd>
      </template>
      <dt>Symbol</dt>
      <dd>
        {{ row.symbol_name }} <span class="muted mono">{{ row.symbol_table }}{{ row.symbol_code }}</span>
      </dd>
      <template v-if="position !== null">
        <dt>Position</dt>
        <dd>{{ position }}</dd>
      </template>
      <template v-if="fromUs !== null">
        <dt>From us</dt>
        <dd>{{ fromUs }}</dd>
      </template>
      <template v-if="row.course_deg !== null">
        <dt>Course</dt>
        <dd>{{ courseText(row.course_deg) }}</dd>
      </template>
      <template v-if="row.speed_kmh !== null">
        <dt>Speed</dt>
        <dd>{{ speedText(row.speed_kmh) }}</dd>
      </template>
      <template v-if="row.altitude_m !== null">
        <dt>Altitude</dt>
        <dd>{{ altitudeText(row.altitude_m) }}</dd>
      </template>
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
        <dd :title="agoText(row.telemetry_at, now)">{{ telemetryText(row.telemetry) }}</dd>
        <dt>Bits</dt>
        <dd>{{ telemetryBitsText(row.telemetry) }}</dd>
      </template>
      <dt>Last heard</dt>
      <dd>{{ agoText(row.last_heard, now) }}</dd>
      <template v-if="row.last_position_at !== null">
        <dt>Last position</dt>
        <dd>{{ agoText(row.last_position_at, now) }}<span v-if="timedOut(aging, row, now)" class="timedword"> - timed out</span></dd>
      </template>
      <dt>First heard</dt>
      <dd>{{ dateTimeText(row.first_heard) }}</dd>
      <template v-if="row.last_path.length > 0">
        <dt>Path</dt>
        <dd class="mono">{{ pathText(row.last_path) }}</dd>
      </template>
      <template v-if="row.last_route">
        <dt>Route</dt>
        <dd>{{ row.last_route }}</dd>
      </template>
      <template v-if="heard !== '-'">
        <dt>Heard</dt>
        <dd>{{ heard }}</dd>
      </template>
      <template v-if="direct !== null">
        <dt>Direct</dt>
        <dd>{{ direct }}</dd>
      </template>
      <template v-if="best !== '-'">
        <dt>Best route</dt>
        <dd>{{ best }}</dd>
      </template>
      <template v-if="row.last_status">
        <dt>Status</dt>
        <dd>{{ row.last_status }}</dd>
      </template>
      <template v-if="row.last_comment">
        <dt>Comment</dt>
        <dd>{{ row.last_comment }}</dd>
      </template>
      <dt>Packets</dt>
      <dd>{{ row.packets }}</dd>
    </dl>
    <div v-if="!row.is_me && !row.own" class="card-path">
      <StationTimeout :call="row.call" :aging="aging" @set="(c, m) => emit('timeout', c, m)" @clear="emit('clearTimeout', $event)" />
    </div>
    <footer v-if="row.own" class="card-foot">
      <button class="btn primary" type="button" @click="emit('edit', row.call)">Edit</button>
      <button class="btn forget" :class="{ danger: armed }" type="button" @click="kill">{{ armed ? "Really kill?" : "Kill" }}</button>
    </footer>
    <footer v-else-if="!row.is_me" class="card-foot">
      <button v-if="row.kind === 'station'" class="btn primary" type="button" @click="emit('message', row.call)">Message</button>
      <button class="btn forget" :class="{ danger: armed }" type="button" @click="forget">{{ armed ? "Really forget?" : "Forget" }}</button>
    </footer>
  </section>
</template>
