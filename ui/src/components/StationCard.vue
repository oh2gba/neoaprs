<script setup lang="ts">
// Everything the daemon knows of one station, as a card over the map: the symbol, the position, how far and in which direction from us, how it moves, when it was heard, the path of its latest
// packet and the route it came by, how its packets reached us (direct, by which repeaters, from the internet), when it was last heard direct and the share of its packets that came direct, and the best route with the path to send by, its status and comment, how many packets it sent. "Message" opens the Messages tab with the station as the addressee; the path field is the path its messages go by, the timeout field how long
// it stays on the map and the attempts field how many times a message to it is transmitted. The details that the daemon decodes beyond the position follow the altitude, a line each: the data extensions (PHG, range, DF, area), the Maidenhead locator of its status, and the telemetry channels with the names and units it defined. A weather station (the weather symbol, or one that has sent weather) has its weather panel at the top (components/WeatherPanel.vue). "Forget" takes it out of the station book (it is back when it is heard again); it asks twice, and forgets the first click after 5 s like the other buttons that ask twice (`useSure`).
import { computed, watch } from "vue";
import StationPrefs from "@/components/StationPrefs.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import WeatherPanel from "@/components/WeatherPanel.vue";
import { useSure } from "@/composables/useSure";
import { timedOut, type Aging } from "@/lib/aging";
import type { Attempts } from "@/lib/attempts";
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
    attempts?: Attempts;
    paths?: ReadonlyMap<string, string>;
    fallbackPath?: string;
    rfOnly?: ReadonlySet<string>;
    weatherSeries?: WeatherSeriesMessage | null;
  }>(),
  {
    aging: () => ({ timeouts: new Map<string, number>(), defaultMin: 0 }),
    attempts: () => ({ own: new Map<string, number>(), defaultCount: 6 }),
    paths: () => new Map<string, string>(),
    fallbackPath: "",
    rfOnly: () => new Set<string>(),
    weatherSeries: null,
  },
);
const emit = defineEmits<{
  forget: [call: string];
  message: [call: string];
  path: [call: string, path: string];
  clearPath: [call: string];
  timeout: [call: string, minutes: number];
  clearTimeout: [call: string];
  setAttempts: [call: string, attempts: number];
  clearAttempts: [call: string];
  setRfOnly: [call: string, on: boolean];
  weather: [call: string, hours: number];
  close: [];
}>();

const sure = useSure<string>();
watch(() => props.row.call, sure.disarm);

const armed = computed(() => sure.armed.value === props.row.call);
const forget = (): void => sure.press(props.row.call, () => emit("forget", props.row.call));

const qrz = computed(() => (props.row.kind === "station" ? qrzUrl(props.row.call) : null));
const extensions = computed(() => extensionRows(props.row.extensions));
const fromUs = (row: StationRow): string => (row.distance_km === null ? "-" : `${distanceText(row.distance_km)} km, ${bearingText(row.bearing_deg)}`);
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
        <span class="muted">{{ row.symbol_name }}{{ row.is_me ? " (our station)" : "" }}</span>
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
      <dt>Position</dt>
      <dd>{{ positionText(row.lat, row.lon) }}</dd>
      <dt>From us</dt>
      <dd>{{ fromUs(row) }}</dd>
      <dt>Course</dt>
      <dd>{{ courseText(row.course_deg) }}</dd>
      <dt>Speed</dt>
      <dd>{{ speedText(row.speed_kmh) }}</dd>
      <dt>Altitude</dt>
      <dd>{{ altitudeText(row.altitude_m) }}</dd>
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
      <dt>Last position</dt>
      <dd>{{ agoText(row.last_position_at, now) }}<span v-if="timedOut(aging, row, now)" class="timedword"> - timed out</span></dd>
      <dt>First heard</dt>
      <dd>{{ dateTimeText(row.first_heard) }}</dd>
      <dt>Path</dt>
      <dd class="mono">{{ pathText(row.last_path) }}</dd>
      <dt>Route</dt>
      <dd>{{ row.last_route || "-" }}</dd>
      <dt>Heard</dt>
      <dd>{{ heardText(row) }}</dd>
      <dt>Direct</dt>
      <dd>{{ row.kind === "station" && !row.is_me ? directWords(row, now) : "-" }}</dd>
      <dt>Best route</dt>
      <dd>{{ bestText(row) }}</dd>
      <dt>Status</dt>
      <dd>{{ row.last_status || "-" }}</dd>
      <dt>Comment</dt>
      <dd>{{ row.last_comment || "-" }}</dd>
      <dt>Packets</dt>
      <dd>{{ row.packets }}</dd>
    </dl>
    <div v-if="!row.is_me" class="card-path">
      <StationPrefs
        :call="row.call"
        :aging="aging"
        :attempts="attempts"
        :paths="paths"
        :fallback-path="fallbackPath"
        :rf-only="rfOnly"
        :with-path="row.kind === 'station'"
        :suggested="row.suggested_path"
        @clear-path="emit('clearPath', $event)"
        @clear-timeout="emit('clearTimeout', $event)"
        @clear-attempts="emit('clearAttempts', $event)"
        @path="(c, p) => emit('path', c, p)"
        @timeout="(c, m) => emit('timeout', c, m)"
        @set-attempts="(c, n) => emit('setAttempts', c, n)"
        @set-rf-only="(c, on) => emit('setRfOnly', c, on)"
      />
    </div>
    <footer v-if="!row.is_me" class="card-foot">
      <button v-if="row.kind === 'station'" class="btn primary" type="button" @click="emit('message', row.call)">Message</button>
      <button class="btn forget" :class="{ danger: armed }" type="button" @click="forget">{{ armed ? "Really forget?" : "Forget" }}</button>
    </footer>
  </section>
</template>
