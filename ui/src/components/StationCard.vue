<script setup lang="ts">
// What the daemon knows of one station, as a card over the map, in the few facts a person asks for: the symbol with its name and a green check mark beside the call for a station that was heard direct (no repeater), when it was last heard, for each way it was heard ("RF 3 min ago · Internet 40 s ago"; lib/channels.ts; the full time of the latest when the mouse rests on it), the position and how far and in which direction it is from us, how fast it moves (only a station that does),
// the altitude, the voice frequency with its tone, offset and range (when it gave one), the status and the comment, what it runs ("Kenwood TH-D74", "APRSdroid"; only when the device list knows it), one line of how its packets reach us ("Reached us via OH2RCH-2", or "direct"; none for a station known from the internet alone) and one for the internet ("Heard by iGate OH2GW-10 via OH2RCH-2", "Sent from an internet app, never on the air"; for a station that came over it) and, for such a station, that a message to it is not possible. A row with nothing to say is left out. The rest is under "Details", closed (components/StationDetails.vue: the path as it was sent, the counts of the routes, the best route, when it was first heard, the packets, the decoded extras).
// A weather station (the weather symbol, or one that has sent weather) has its weather panel at the top (components/WeatherPanel.vue). "Message" opens the Messages tab with the station as the addressee, where the path its messages go by and RF only are set.
// The pin beside the cross (a tablet and a desktop) keeps the card on the map past Esc and Close all and past a reload, until its cross is clicked (the cross unpins and closes it).
// Several cards can be open (Ctrl+click, components/StationCards.vue), side by side: each is this whole card, as when it is alone. Forget (the trash can, "Forget OH2XYZ") takes it out of the station book (it is back when it is heard again); it asks twice ("sure?"), and forgets the first click after 5 s like the other buttons that ask twice (`useSure`). An object or an item of ours has "Edit" (the Objects tab opens with it) and "Kill" (it asks twice, too) in place of "Message" and "Forget", and none of the fields of a station that is heard.
import { computed, watch } from "vue";
import IconButton from "@/components/IconButton.vue";
import MessageGlyph from "@/components/MessageGlyph.vue";
import DirectMark from "@/components/DirectMark.vue";
import RouteText from "@/components/RouteText.vue";
import StationDetails from "@/components/StationDetails.vue";
import SymbolIcon from "@/components/SymbolIcon.vue";
import WeatherPanel from "@/components/WeatherPanel.vue";
import { useSure } from "@/composables/useSure";
import { t } from "@/i18n";
import { timedOut, type Aging } from "@/lib/aging";
import { qrzUrl } from "@/lib/calls";
import { heardByChannel, internetOnly } from "@/lib/channels";
import { frequencyText } from "@/lib/details";
import { heardDirect, internetText, reachedText } from "@/lib/routes";
import { canForget, canMessage, symbolLabel } from "@/lib/stations";
import { agoWords, altitudeText, bearingText, dateTimeText, distanceText, positionText, speedText } from "@/lib/format";
import { isWeatherStation, type Ranges } from "@/lib/weather";
import type { StationRow, WeatherSeriesMessage } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{
    row: StationRow;
    /** The stations of the book, to know whether the iGate that heard the station has a place. */
    stations?: ReadonlyMap<string, StationRow>;
    now: number;
    aging?: Aging;
    weatherSeries?: WeatherSeriesMessage | null;
    /** The value axes the open weather cards share. */
    ranges?: Ranges;
    /** The card can be moved by its head (a tablet and a desktop; the bottom sheet of a phone cannot), and pinned. */
    movable?: boolean;
    /** The card is pinned: it stays on the map until its cross is clicked. */
    pinned?: boolean;
  }>(),
  {
    stations: () => new Map(),
    aging: () => ({ defaultMin: 0 }),
    weatherSeries: null,
    ranges: undefined,
    movable: false,
    pinned: false,
  },
);
const emit = defineEmits<{
  forget: [call: string];
  edit: [name: string];
  kill: [name: string];
  message: [call: string];
  pin: [];
  weather: [call: string, hours: number];
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
    : t("station.from_us_value", { distance: distanceText(props.row.distance_km), bearing: bearingText(props.row.bearing_deg) }),
);
const position = computed(() => (props.row.lat === null || props.row.lon === null ? null : positionText(props.row.lat, props.row.lon)));
/** Only a station that moves has a speed and a course worth saying: "85 km/h, course 96° E". */
const moving = computed(() => {
  const { speed_kmh: speed, course_deg: course } = props.row;
  if (speed === null || speed <= 0) return null;
  return course === null ? speedText(speed) : t("station.speed_course", { speed: speedText(speed), course: bearingText(course) });
});
/** When it was last heard by each channel: "RF 3 min ago · Internet 40 s ago"; the plain age for a row nothing was counted for. */
const heardOn = computed(() => heardByChannel(props.row, props.now) || agoWords(props.row.last_heard, props.now));
const weather = computed(() => isWeatherStation(props.row));
const heardStation = computed(() => props.row.kind === "station" && !props.row.is_me && !props.row.own);
const reached = computed(() => (heardStation.value ? reachedText(props.row) : null));
/** How its latest packet over the internet got there, its own line (a station heard both ways has this and the radio's). */
const internet = computed(() => (heardStation.value ? internetText(props.row, props.stations) : null));
</script>

<template>
  <section class="card" :aria-label="t('station.card.label')">
    <header class="card-head" :title="movable ? t('station.card.drag_title') : undefined">
      <SymbolIcon :table="row.symbol_table" :code="row.symbol_code" :size="32" />
      <div class="card-title">
        <span class="card-call">
          <strong>{{ row.call }}</strong>
          <DirectMark v-if="heardDirect(row)" />
          <a v-if="qrz" class="qrz" :href="qrz" target="_blank" rel="noopener noreferrer" :title="t('station.card.qrz_title')">QRZ</a>
        </span>
        <span class="muted">{{ symbolLabel(row, true) }}</span>
      </div>
      <IconButton v-if="movable" kind="pin" class="card-pin" :pressed="pinned" :label="t('iconbutton.pin')" @click="emit('pin')" />
      <IconButton kind="close" class="card-close" :label="t('iconbutton.close')" @click="emit('close')" />
    </header>
    <div class="card-body">
      <WeatherPanel v-if="weather" :row="row" :series="weatherSeries" :now="now" :ranges="ranges" @ask="(c, h) => emit('weather', c, h)" />
      <dl class="card-fields">
        <template v-if="row.kind !== 'station'">
          <dt>{{ t("station.field.kind") }}</dt>
          <dd>{{ t("station.kind_reported", { kind: t(`station.kind.${row.kind}`), by: row.reported_by || "-" }) }}</dd>
        </template>
        <dt>{{ t("station.field.last_heard") }}</dt>
        <dd :title="dateTimeText(row.last_heard)">{{ heardOn }}</dd>
        <template v-if="position !== null">
          <dt>{{ t("station.field.position") }}</dt>
          <dd>
            {{ position }}<span v-if="timedOut(aging, row, now)" class="timedword">{{ ` - ${t("station.timed_out")}` }}</span>
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
          <dd>{{ altitudeText(row.altitude_m) }}</dd>
        </template>
        <template v-if="row.frequency !== null">
          <dt>{{ t("station.field.frequency") }}</dt>
          <dd>{{ frequencyText(row.frequency) }}</dd>
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
      <StationDetails :row="row" />
    </div>
    <footer v-if="row.own" class="card-foot">
      <button class="btn primary" type="button" @click="emit('edit', row.call)">{{ t("station.card.edit") }}</button>
      <button class="btn forget" :class="{ danger: armed }" type="button" @click="kill">
        {{ armed ? t("station.card.kill_sure") : t("station.card.kill") }}
      </button>
    </footer>
    <footer v-else-if="canForget(row)" class="card-foot">
      <button v-if="canMessage(row)" class="btn primary msgbtn card-message" type="button" @click="emit('message', row.call)">
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
  </section>
</template>
