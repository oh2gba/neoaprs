<script setup lang="ts">
// What the daemon knows of one station, as a card over the map: symbol, name, call (with a check
// mark when heard direct), last heard per channel, altitude, voice frequency, PHG or range, status,
// comment, the device it runs, and how its packets reach us. A weather station has a weather panel
// at the top (WeatherPanel). A heard station shows packets per hour (StationPackets), a moving one
// its speed (StationSpeed), and one whose radio measured the signal shows the signal. Objects and
// items have neither the packets chart nor the signal; ours is what we send. "Message" opens the
// Messages tab with the station as addressee. A station with an alert has a quiet bell (AlertBell)
// by its call. The pin beside the cross (tablet and desktop) keeps the card past Esc, Close all and
// a reload. The head is the drag handle and not selectable; a right-click offers to copy the call
// (CopyMenu). Several cards can be open (Ctrl+click, StationCards). Forget removes the station from
// the book and asks twice, resetting after 5 s (`useSure`).
import { computed, watch } from "vue";
import AlertBell from "@/components/AlertBell.vue";
import TwoWords from "@/components/TwoWords.vue";
import BearingArrow from "@/components/BearingArrow.vue";
import CopyMenu from "@/components/CopyMenu.vue";
import { useRadios } from "@/composables/useRadios";
import IconButton from "@/components/IconButton.vue";
import MessageGlyph from "@/components/MessageGlyph.vue";
import DirectMark from "@/components/DirectMark.vue";
import RouteText from "@/components/RouteText.vue";
import StationDetails from "@/components/StationDetails.vue";
import StationPackets from "@/components/StationPackets.vue";
import StationSignal from "@/components/StationSignal.vue";
import StationSpeed from "@/components/StationSpeed.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import WeatherPanel from "@/components/WeatherPanel.vue";
import { useCopyMenu } from "@/composables/useCopyMenu";
import { useSure } from "@/composables/useSure";
import { t } from "@/i18n";
import { timedOut, type Aging } from "@/lib/aging";
import { qrzUrl } from "@/lib/calls";
import { heardTimes, internetOnly } from "@/lib/channels";
import { extensionRows, frequencyText } from "@/lib/details";
import { heardDirect, internetText, reachedText } from "@/lib/routes";
import { canForget, canMessage, symbolLabel } from "@/lib/stations";
import { HOUR_MS, agoWords, bearingText, dateTimeText, positionText } from "@/lib/format";
import { distanceWithUnit, heightText, speedText } from "@/lib/units";
import { isWeatherStation, type Ranges } from "@/lib/weather";
import { SIGNAL_HOURS, readingText } from "@/lib/signal";
import { isMoving, tripStart } from "@/lib/speed";
import type {
  AlertWhen,
  PacketHistoryMessage,
  SignalSeriesMessage,
  SpeedSeriesMessage,
  StationRow,
  WeatherSeriesMessage,
} from "@/protocol/protocol";

const radios = useRadios();
const props = withDefaults(
  defineProps<{
    row: StationRow;
    /** The stations of the book, to know whether the iGate that heard the station has a place. */
    stations?: ReadonlyMap<string, StationRow>;
    now: number;
    aging?: Aging;
    weatherSeries?: WeatherSeriesMessage | null;
    /** The station's packets by the hour, the daemon's latest answer. */
    packetHistory?: PacketHistoryMessage | null;
    /** The speeds of a moving station, the daemon's latest answer. */
    speedSeries?: SpeedSeriesMessage | null;
    /** The readings of the station's signal, the daemon's latest answer. */
    signalSeries?: SignalSeriesMessage | null;
    /** The value axes the open weather cards share. */
    ranges?: Ranges;
    /**
     * The card can be moved by its head and pinned (tablet and desktop; not the phone's bottom
     * sheet).
     */
    movable?: boolean;
    /** The card is pinned: it stays on the map until its cross is clicked. */
    pinned?: boolean;
    /**
     * The alert the operator set on the station (a bell at the end of the call line); null for
     * none.
     */
    alert?: AlertWhen | null;
  }>(),
  {
    stations: () => new Map(),
    aging: () => ({ defaultMin: 0 }),
    weatherSeries: null,
    packetHistory: null,
    speedSeries: null,
    signalSeries: null,
    ranges: undefined,
    movable: false,
    pinned: false,
    alert: null,
  },
);
const emit = defineEmits<{
  forget: [call: string];
  edit: [name: string];
  kill: [name: string];
  message: [call: string];
  pin: [];
  weather: [call: string, hours: number];
  packets: [call: string];
  speed: [call: string];
  signal: [call: string];
  close: [];
}>();

const sure = useSure<string>();
watch(() => props.row.call, sure.disarm);

const armed = computed(() => sure.armed.value === props.row.call);
const forget = (): void => sure.press(props.row.call, () => emit("forget", props.row.call));
const kill = (): void => sure.press(props.row.call, () => emit("kill", props.row.call));

const qrz = computed(() => (props.row.kind === "station" ? qrzUrl(props.row.call) : null));
const fromUs = computed(() =>
  props.row.distance_km === null
    ? null
    : t("station.from_us_value", {
        distance: distanceWithUnit(props.row.distance_km),
        bearing: bearingText(props.row.bearing_deg),
      }),
);
const position = computed(() =>
  props.row.lat === null || props.row.lon === null ? null : positionText(props.row.lat, props.row.lon),
);
/** Only a moving station has a speed and course worth saying: "85 km/h, course 96° E". */
const moving = computed(() => {
  const { speed_kmh: speed, course_deg: course } = props.row;
  if (speed === null || speed <= 0) return null;
  return course === null
    ? speedText(speed)
    : t("station.speed_course", { speed: speedText(speed), course: bearingText(course) });
});
/**
 * When it was last heard per radio and channel: "FM 3 min ago · Internet 40 s ago"; the plain age
 * for a row nothing was counted for.
 */
const heardOn = computed(
  () => heardTimes(props.row, radios.all.value, props.now) || agoWords(props.row.last_heard, props.now),
);
/**
 * The signal of the latest packet heard direct that a radio measured, with its age ("SNR −3 dB, 5
 * min ago"); null without a reading, and for objects, items and ours.
 */
const signal = computed(() => {
  if (!heardStation.value) return null;
  const { snr, rssi, signal_at: at } = props.row;
  const reading = readingText({ snr, rssi });
  return reading === null || at === null ? null : t("station.signal_value", { reading, ago: agoWords(at, props.now) });
});
const weather = computed(() => isWeatherStation(props.row));
const heardStation = computed(() => props.row.kind === "station" && !props.row.is_me && !props.row.own);
/**
 * The signal graph, for a heard station whose latest reading is within the graph's day; decided
 * from the row so that its room exists before the answer.
 */
const signalGraph = computed(
  () =>
    heardStation.value &&
    props.row.signal_at !== null &&
    Date.parse(props.row.signal_at) >= props.now - SIGNAL_HOURS * HOUR_MS,
);
const reached = computed(() => (heardStation.value ? reachedText(props.row) : null));
/**
 * The PHG, range, DF or area the station gave, one row each; the last given is kept until another
 * comes.
 */
const extensions = computed(() => extensionRows(props.row.extensions));

/** The copy menu of the head: the call. */
const copy = useCopyMenu(() => [{ kind: "call", text: props.row.call }]);
/** How its latest packet over the internet got there, on its own line. */
const internet = computed(() => (!props.row.is_me && !props.row.own ? internetText(props.row, props.stations) : null));
</script>

<template>
  <section class="card" :aria-label="t('station.card.label')">
    <header class="card-head" :title="movable ? t('station.card.drag_title') : undefined" v-on="copy.on.value">
      <SymbolIcon :table="row.symbol_table" :code="row.symbol_code" :size="32" />
      <div class="card-title">
        <span class="card-call">
          <strong>{{ row.call }}</strong>
          <DirectMark v-if="heardDirect(row)" />
          <a
            v-if="qrz"
            class="qrz"
            :href="qrz"
            target="_blank"
            rel="noopener noreferrer"
            :title="t('station.card.qrz_title')"
            >QRZ</a
          >
          <AlertBell v-if="alert" :alert="alert" />
        </span>
        <span class="muted">{{ symbolLabel(row, true) }}</span>
      </div>
      <IconButton
        v-if="movable"
        kind="pin"
        class="card-pin"
        :pressed="pinned"
        :label="t('iconbutton.pin')"
        @click="emit('pin')"
      />
      <IconButton kind="close" class="card-close" :label="t('iconbutton.close')" @click="emit('close')" />
    </header>
    <div class="card-body">
      <WeatherPanel
        v-if="weather"
        :row="row"
        :series="weatherSeries"
        :now="now"
        :ranges="ranges"
        @ask="(c, h) => emit('weather', c, h)"
      />
      <dl class="card-fields">
        <template v-if="row.kind !== 'station'">
          <dt>{{ t("station.field.kind") }}</dt>
          <dd>{{ t("station.kind_reported", { kind: t(`station.kind.${row.kind}`), by: row.reported_by || "-" }) }}</dd>
        </template>
        <dt>{{ t("station.field.last_heard") }}</dt>
        <dd :title="dateTimeText(row.last_heard)">{{ heardOn }}</dd>
        <template v-if="signal !== null">
          <dt>{{ t("station.field.signal") }}</dt>
          <dd :title="dateTimeText(row.signal_at ?? row.last_heard)">{{ signal }}</dd>
        </template>
        <template v-if="position !== null">
          <dt>{{ t("station.field.position") }}</dt>
          <dd>
            {{ position
            }}<span v-if="timedOut(aging, row, now)" class="timedword">{{ ` - ${t("station.timed_out")}` }}</span>
          </dd>
        </template>
        <template v-if="fromUs !== null">
          <dt>{{ t("station.field.from_us") }}</dt>
          <dd>{{ fromUs }}</dd>
        </template>
        <template v-if="moving !== null">
          <dt>{{ t("station.field.speed") }}</dt>
          <dd>{{ moving }}</dd>
        </template>
        <template v-if="row.altitude_m !== null">
          <dt>{{ t("station.field.altitude") }}</dt>
          <dd>{{ heightText(row.altitude_m) }}</dd>
        </template>
        <template v-if="row.frequency !== null">
          <dt>{{ t("station.field.frequency") }}</dt>
          <dd>{{ frequencyText(row.frequency) }}</dd>
        </template>
        <template v-for="ext in extensions" :key="ext.label">
          <dt>{{ ext.label }}</dt>
          <dd>
            {{ ext.text }}
            <span v-if="ext.direction" class="antenna" :title="ext.direction.title"
              ><BearingArrow :deg="ext.direction.deg" :label="ext.direction.title"
            /></span>
          </dd>
        </template>
        <template v-if="row.last_status">
          <dt>{{ t("station.field.status") }}</dt>
          <dd>{{ row.last_status }}</dd>
        </template>
        <template v-if="row.last_comment">
          <dt>{{ t("station.field.comment") }}</dt>
          <dd>{{ row.last_comment }}</dd>
        </template>
        <template v-if="row.device !== ''">
          <dt>{{ t("station.field.device") }}</dt>
          <dd>{{ row.device }}</dd>
        </template>
        <template v-if="reached !== null">
          <dt>{{ t("station.field.reached") }}</dt>
          <dd><RouteText :text="reached" /></dd>
        </template>
        <template v-if="internet !== null">
          <dt>{{ t("station.field.internet") }}</dt>
          <dd><RouteText :text="internet" /></dd>
        </template>
        <template v-if="row.kind === 'station' && internetOnly(row)">
          <dt>{{ t("station.field.messages") }}</dt>
          <dd>{{ t("station.messages_internet_only") }}</dd>
        </template>
      </dl>
      <StationPackets v-if="heardStation" :history="packetHistory" :now="now" @ask="emit('packets', row.call)" />
      <StationSpeed
        v-if="heardStation && isMoving(row, now)"
        :position-at="row.last_position_at"
        :series="speedSeries"
        :from="tripStart(row, now)"
        :now="now"
        @ask="emit('speed', row.call)"
      />
      <StationSignal
        v-if="signalGraph"
        :signal-at="row.signal_at ?? null"
        :series="signalSeries"
        :measured="row.snr === null && row.rssi !== null ? 'rssi' : 'snr'"
        :now="now"
        @ask="emit('signal', row.call)"
      />
      <StationDetails :row="row" />
    </div>
    <footer v-if="row.own" class="card-foot">
      <button class="btn primary" type="button" @click="emit('edit', row.call)">{{ t("station.card.edit") }}</button>
      <button class="btn forget" :class="{ danger: armed }" type="button" @click="kill">
        <TwoWords :second="armed">
          <template #first>{{ t("station.card.kill") }}</template>
          <template #second>{{ t("station.card.kill_sure") }}</template>
        </TwoWords>
      </button>
    </footer>
    <footer v-else-if="canForget(row)" class="card-foot">
      <button
        v-if="canMessage(row)"
        class="btn primary msgbtn card-message"
        type="button"
        @click="emit('message', row.call)"
      >
        <MessageGlyph :size="14" /> {{ t("station.card.message") }}
      </button>
      <IconButton
        kind="delete"
        class="card-forget"
        :armed="armed"
        :label="t('station.card.forget', { call: row.call })"
        :title="t('station.card.forget', { call: row.call })"
        @click="forget"
      />
    </footer>
    <CopyMenu v-if="copy.menu.value" :key="copy.key.value" v-bind="copy.menu.value" @close="copy.close()" />
  </section>
</template>
