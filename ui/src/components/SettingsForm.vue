<script setup lang="ts">
// The daemon's settings, one field per key in the form's scope (the Settings tab, or the My station
// tab with the keys the beacon sends), in groups (SettingsGroup). There is no Save button: a choice
// applies at once and a typed field on Enter or blur, after the page's check and then the daemon's;
// a wrong one shows under its field with the typed text kept. The Undo toast and screen-reader line
// belong to useSettings, shared with the other tab. Slots: `top` (beacon status above the first
// group), `status` (the send-status line), and more groups from the page. The alert command has a
// Test button; a page of another device has neither the command nor the test. The Map group has
// Radius and the Detailed map row with MapFetchButton and MapFetchNotes. The My station Station
// group starts with where the position comes from (gps/source) and shows the place only for Fixed;
// the Beacon group has the Beacon choice and, for a moving station, Travelling. Notifications
// group: BrowserAlerts. The Internet group has the Enable tickbox and a status row, and asks to set
// the call first. The Web page group has the access key with a New key button and the PhoneCode.
// The Encrypted messages group appears only while the daemon runs with --encryption.
import BrowserAlerts from "@/components/BrowserAlerts.vue";
import TwoWords from "@/components/TwoWords.vue";
import ConfirmRow from "@/components/ConfirmRow.vue";
import MapFetchButton from "@/components/MapFetchButton.vue";
import MapFetchNotes from "@/components/MapFetchNotes.vue";
import ActionRow from "@/components/ActionRow.vue";
import DigipeaterStatus from "@/components/DigipeaterStatus.vue";
import IgateStatus from "@/components/IgateStatus.vue";
import UpdateRow from "@/components/UpdateRow.vue";
import { internetStations } from "@/lib/igatestatus";
import InfoTip from "@/components/InfoTip.vue";
import LanguageField from "@/components/LanguageField.vue";
import SettingsField from "@/components/SettingsField.vue";
import SettingsFold from "@/components/SettingsFold.vue";
import SettingsLocation from "@/components/SettingsLocation.vue";
import SettingsBox from "@/components/SettingsBox.vue";
import SettingsAbout from "@/components/SettingsAbout.vue";
import SettingsGroup from "@/components/SettingsGroup.vue";
import SettingsHelp from "@/components/SettingsHelp.vue";
import SettingsHttps from "@/components/SettingsHttps.vue";
import SettingsLayer from "@/components/SettingsLayer.vue";
import SettingsPort from "@/components/SettingsPort.vue";
import PhoneCode from "@/components/PhoneCode.vue";
import SymbolField from "@/components/SymbolField.vue";
import SettingsRadio from "@/components/SettingsRadio.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { ALERT_KEY, useAlertTest } from "@/composables/useAlertTest";
import { KEY_KEY, useNewKey } from "@/composables/useNewKey";
import { useSure } from "@/composables/useSure";
import { useUpdateCheck } from "@/composables/useUpdateCheck";
import { useSettingsForm } from "@/composables/useSettingsForm";
import type { Picked } from "@/composables/usePositionPick";
import { disabledByValues } from "@/lib/beaconoff";
import { degreesText, roundPlace, wrapLongitude } from "@/lib/setup";
import { portsAsks } from "@/lib/radios";
import {
  BEACON_FOLDS,
  SUBGROUPS,
  fieldFor,
  igateOn,
  shownByValues,
  storedFor,
  valueFor,
  type Scope,
} from "@/lib/settings";
import { layerKey } from "@/lib/layersettings";
import { boxedKey, digiPlaces, inputId, radioFieldOf, shownByRadios, shownFor } from "@/lib/settingsradio";
import { UNITS_KEY } from "@/lib/units";
import { useRadios } from "@/composables/useRadios";
import { holderOf } from "@/lib/portchoice";
import { keyLink } from "@/lib/access";
import { statusSource } from "@/lib/status";
import { settingLimit } from "@/lib/textlimit";
import { computed, watch } from "vue";

const props = withDefaults(defineProps<{ scope?: Scope; picking?: boolean; picked?: Picked | null }>(), {
  scope: "settings",
  picking: false,
  picked: null,
});
const emit = defineEmits<{ setup: []; update: []; notes: []; pickPosition: [] }>();

const {
  config,
  lastError,
  send,
  settings,
  alertResult,
  updateResult,
  map,
  alerts,
  ports,
  say,
  igate,
  stations,
  keys,
  local,
  connection,
} = useDaemonContext();
// New key asks twice: stations holding the old key must be sent the new one.
const newMessageKey = useSure<string>();
const { draft, errors } = settings;
const form = useSettingsForm(config, settings, props.scope);
const { groups, question, defaults } = form;
const alertTest = useAlertTest(
  alertResult,
  lastError,
  send,
  draft,
  computed(() => config.value?.values[ALERT_KEY]),
  connection,
);
const updateCheck = useUpdateCheck(updateResult, lastError, send, connection);
const newKey = useNewKey();
const RADIUS_KEY = "map/radius_km";
const SYMBOL_TABLE = "station/symbol_table";
const SYMBOL_CODE = "station/symbol_code";
const GPS_DEVICE = "gps/device";
const info = (key: string) => fieldFor(key, draft);
/**
 * A field the My station tab greys out while the beacon is Off (shown with its value, not
 * changeable).
 */
const greyed = (key: string): boolean =>
  props.scope === "beacon" &&
  disabledByValues(key, draft, radios.enabled.value.length > 0 && radios.senders.value.length === 0);
/**
 * The network is let in and the daemon has made a key (what is in force, not the switch being
 * changed).
 */
const network = computed(
  () => config.value?.values["web/network"] === "true" && (config.value.values[KEY_KEY] ?? "") !== "",
);
/**
 * What the phone code holds: the page's first address for other devices (the one on the network,
 * else the .local name) with the access key in force.
 */
const phoneLink = computed(() => keyLink(config.value?.urls[0] ?? "", config.value?.values[KEY_KEY] ?? ""));
/**
 * Our call in force (the iGate logs in as it; the passcode page is told it); the iGate group asks
 * for it first.
 */
const call = computed(() => (config.value?.values["station/call"] ?? "").trim());
// the answers of the buttons (Test, New key) are said in the toast so that nothing moves; the
// answer of Check now is in its row
for (const answer of [alertTest.result, newKey.result]) watch(answer, (result) => result && say(result.text));
/**
 * The keys the Beacon group keeps behind closed headings (antenna, path); they are not in its own
 * list.
 */
const folded = new Set(props.scope === "beacon" ? BEACON_FOLDS.flatMap((fold) => fold.keys) : []);
const shown = (keys: readonly string[], inGroup = true) =>
  keys.filter(
    (key) =>
      key !== SYMBOL_CODE &&
      !(key === "station/lon" && props.scope === "beacon") &&
      !(inGroup && folded.has(key)) &&
      (key !== ALERT_KEY || local.value) &&
      shownFor(key, network.value) &&
      shownByRadios(key, radios.all.value) &&
      shownByValues(key, draft),
  );
const radios = useRadios();
/**
 * The GPS receiver's Refresh asks for the ports by the radios that have sound cards, so that their
 * boxes keep their cards.
 */
const askPorts = () => portsAsks(radios.all.value.map((radio) => radio.row)).forEach((ask) => send(ask));
/** Who holds a port, for the GPS receiver's: a radio by its name. */
const gpsHolder = holderOf(0, (id) => radios.byId(id)?.name);
/**
 * The Digipeater group: an Enable per radio that may repeat and is on (boxed with the radio's
 * legend where there are several, with its counts), then a box per pair of radios with Enable, Call
 * and counts.
 */
const digi = computed(() => digiPlaces(radios.all.value, draft));
/**
 * The groups with something to show: the Digipeater group only while a radio that may repeat, or a
 * pair, is on.
 */
const drawn = computed(() => groups.value.filter((group) => group.id !== "digi" || digi.value.keys.length > 0));
/** The keys of a group's own fields that are shown (the Digipeater group's are its radios'). */
const keysOf = (group: { id: string; keys: readonly string[] }) =>
  group.id === "digi" ? digi.value.keys : shown(group.keys);
/** The symbol is one field, which sets the table and the code. */
const symbol = computed(() => `${draft[SYMBOL_TABLE] ?? ""}${draft[SYMBOL_CODE] ?? ""}`);
function editSymbol(text: string): void {
  settings.edit(SYMBOL_TABLE, text.slice(0, 1));
  settings.edit(SYMBOL_CODE, text.slice(1, 2));
}
// a place picked on the map (Choose on map) is our latitude and longitude, sent together
watch(
  () => props.picked,
  (at) => {
    if (!at) return;
    settings.change({
      "station/lat": degreesText(roundPlace(at.lat)),
      "station/lon": degreesText(wrapLongitude(at.lon)),
    });
  },
);
/** Only the Settings tab folds its groups. */
const folds = props.scope === "settings";
/**
 * A group opens by itself when the person must see it: a complaint about one of its fields, or a
 * question about one.
 */
const needsLook = (groupKeys: readonly string[]): boolean =>
  groupKeys.some((key) => (errors[key] ?? "") !== "" || question.value?.key === key);
/** A key of a box the Radio group shows: of a radio that is there and not removed. */
const inBox = (key: string): boolean => {
  const id = radioFieldOf(key)?.id;
  return boxedKey(key) && id !== undefined && radios.byId(id)?.removed === false;
};
/**
 * The fields that open a group: the Digipeater group's are its radios', the Radio group's its own
 * and its boxes'.
 */
const lookKeys = (group: { id: string; keys: readonly string[] }): readonly string[] =>
  group.id === "digi"
    ? digi.value.keys
    : group.id === "serial"
      ? [...group.keys, ...[...Object.keys(errors), question.value?.key ?? ""].filter(inBox)]
      : group.keys;
const fallback = (key: string) => defaults.value[key] ?? "";
/**
 * The keys of a group in boxes: a key with its own heading (the daemon's alert) starts a box with a
 * legend that runs to the end of the group; earlier keys are in no box.
 */
function boxesOf(keys: readonly string[]) {
  const boxes: { id: string; sub: (typeof SUBGROUPS)[string] | null; keys: string[] }[] = [];
  for (const key of keys) {
    const sub = SUBGROUPS[key] ?? digi.value.boxes[key] ?? null;
    if (sub !== null || boxes.length === 0) boxes.push({ id: key, sub, keys: [key] });
    else boxes[boxes.length - 1]?.keys.push(key);
  }
  return boxes;
}
/** A typed field follows the typing; a choice is made by `choose`. */
function typed(key: string, text: string): void {
  const kind = info(key).kind;
  if (kind !== "bool" && kind !== "choice") settings.edit(key, text);
}
</script>

<template>
  <form v-if="config" class="settings" novalidate @submit.prevent>
    <LanguageField v-if="scope === 'settings'" />
    <SettingsField
      v-if="scope === 'settings'"
      :id="inputId(UNITS_KEY)"
      :info="info(UNITS_KEY)"
      :model-value="valueFor(UNITS_KEY, draft)"
      :fallback="fallback(UNITS_KEY)"
      :error="errors[UNITS_KEY] ?? ''"
      :changed="form.changed(UNITS_KEY)"
      :apply="true"
      @update:model-value="typed(UNITS_KEY, $event)"
      @choose="form.choose({ [UNITS_KEY]: $event })"
      @commit="form.finish(UNITS_KEY, $event)"
      @cancel="settings.cancel(UNITS_KEY)"
    />
    <p v-if="scope === 'settings'" class="settings-setup">
      <button class="linkbutton setup-open" type="button" @click="emit('setup')">
        {{ t("settings.setup_again") }}
      </button>
    </p>
    <span class="sr-only" role="status" aria-live="polite"
      ><span :key="settings.announcement.value.n">{{ settings.announcement.value.text }}</span></span
    >
    <SettingsGroup
      v-for="group in drawn"
      :id="group.id"
      :key="group.id"
      :title="group.title"
      :fold="folds"
      :show="needsLook(lookKeys(group))"
    >
      <SettingsRadio v-if="group.id === 'serial'" :settings="settings" :form="form" :defaults="defaults" />
      <p v-if="group.id === 'igate' && call === ''" class="problem" role="status">{{ t("settings.igate.set_call") }}</p>
      <SettingsBox
        v-for="box in boxesOf(group.id === 'serial' || (group.id === 'igate' && call === '') ? [] : keysOf(group))"
        :key="box.id"
        :title="box.sub?.text"
        :hover="box.sub?.title"
      >
        <template v-if="box.sub && box.sub.tip.length > 0" #legend>
          <InfoTip :label="box.sub.tipLabel" :picture="box.sub.picture">
            <span v-for="line in box.sub.tip" :key="line" class="info-line">{{ line }}</span>
          </InfoTip>
        </template>
        <template v-for="key in box.keys" :key="key">
          <SettingsLocation
            v-if="key === 'station/lat'"
            :draft="draft"
            :current="{ lat: config.values['station/lat'] ?? '', lon: config.values['station/lon'] ?? '' }"
            :errors="errors"
            :changed="form.changed"
            :picking="picking"
            @type="settings.edit"
            @commit="form.finish"
            @cancel="settings.cancel"
            @pick="emit('pickPosition')"
          />
          <SymbolField
            v-else-if="key === SYMBOL_TABLE"
            id="set-station-symbol"
            :symbol="symbol"
            :changed="form.changed(SYMBOL_TABLE) || form.changed(SYMBOL_CODE)"
            @update:symbol="editSymbol"
            @commit="settings.commit([SYMBOL_TABLE, SYMBOL_CODE], true)"
          />
          <SettingsPort
            v-else-if="key === GPS_DEVICE"
            :id="inputId(key)"
            :info="info(key)"
            :model-value="draft[key] ?? ''"
            found=""
            :unset="true"
            :ports="ports"
            :holder="gpsHolder"
            :error="errors[key] ?? ''"
            :changed="form.changed(key)"
            @update:model-value="settings.edit(key, $event)"
            @choose="form.choose({ [key]: $event })"
            @commit="form.finish(key, $event)"
            @cancel="settings.cancel(key)"
            @refresh="askPorts"
          />
          <SettingsLayer v-else-if="layerKey(key)" :id="inputId(key)" :field-key="key" :form="form" />
          <SettingsField
            v-else
            :id="inputId(key)"
            :info="info(key)"
            :model-value="key === 'status/source' ? statusSource(draft) : valueFor(key, draft)"
            :fallback="fallback(key)"
            :error="errors[key] ?? ''"
            :changed="form.changed(key)"
            :apply="true"
            :disabled="greyed(key)"
            :count="settingLimit(key, draft)"
            @update:model-value="typed(key, $event)"
            @choose="form.choose({ [key]: storedFor(key, draft, $event) })"
            @commit="form.finish(key, $event)"
            @cancel="settings.cancel(key)"
          >
            <template v-if="key === ALERT_KEY" #after>
              <button
                class="btn"
                type="button"
                :disabled="alertTest.running.value || alertTest.stale.value"
                @click="alertTest.test"
              >
                {{ t("settings.alert_test") }}
              </button>
            </template>
            <template v-else-if="key === KEY_KEY" #after>
              <button
                class="btn"
                :class="{ danger: newKey.armed.value }"
                type="button"
                :disabled="newKey.running.value"
                @click="newKey.press"
              >
                <TwoWords :second="newKey.armed.value">
                  <template #first>{{ t("settings.new_key") }}</template>
                  <template #second>{{ t("settings.new_key_sure") }}</template>
                </TwoWords>
              </button>
            </template>
          </SettingsField>
          <DigipeaterStatus v-if="key in digi.status" v-bind="digi.status[key]" />
          <ActionRow
            v-if="key === RADIUS_KEY && map"
            id="set-map-fetch"
            :label="t('settings.map.detail_label')"
            :tip-label="t('settings.map.tip_label')"
          >
            <MapFetchButton id="set-map-fetch" :map="map" :stale="settings.saving.value" :send="send" />
            <template #tip
              ><span class="info-line">{{ t("settings.map.tip1") }}</span></template
            >
            <template #notes><MapFetchNotes :map="map" /></template>
          </ActionRow>
          <ConfirmRow
            v-if="question?.key === key"
            :message="question.message"
            @yes="form.answer(true)"
            @cancel="form.answer(false)"
          />
          <slot name="after" :field-key="key" :draft="draft"></slot>
          <SettingsHttps v-if="key === 'web/https'" :https="config.https" />
          <div v-if="key === KEY_KEY && phoneLink" class="field">
            <span id="set-web-code-label" class="field-label">{{ t("phone.code.label") }}</span>
            <div class="field-control">
              <PhoneCode :link="phoneLink" labelledby="set-web-code-label" />
              <InfoTip :label="t('phone.code.tip_label')">
                <span class="info-line">{{ t("phone.code.tip1") }}</span>
              </InfoTip>
            </div>
          </div>
        </template>
      </SettingsBox>
      <IgateStatus
        v-if="group.id === 'igate' && call !== '' && igate && igateOn(draft)"
        :igate="igate"
        :values="config.values"
        :stations="internetStations(stations.values())"
      />

      <template v-if="scope === 'beacon'">
        <SettingsFold
          v-for="fold in BEACON_FOLDS.filter((f) => f.group === group.id)"
          :key="fold.title"
          :title="fold.title"
          :keys="shown(fold.keys, false)"
          :settings="settings"
          :form="form"
          :defaults="defaults"
          :disabled="greyed"
        />
      </template>
      <BrowserAlerts v-if="group.id === 'notifications'" :alerts="alerts" :https="config.https" :say="say" />
    </SettingsGroup>
    <SettingsGroup
      v-if="scope === 'settings' && keys.on.value"
      id="encrypt"
      class="encrypt"
      :title="t('settings.group.encrypt')"
    >
      <ActionRow
        id="set-message-key"
        :label="t('settings.encrypt.key_label')"
        :tip-label="t('settings.encrypt.tip_label')"
        picture="encrypt"
      >
        <input id="set-message-key" class="input mono" type="text" readonly :value="keys.own.value" />
        <button
          class="btn"
          :class="{ danger: newMessageKey.armed.value === 'key' }"
          type="button"
          @click="newMessageKey.press('key', () => keys.renew())"
        >
          <TwoWords :second="newMessageKey.armed.value === 'key'">
            <template #first>{{ t("settings.new_key") }}</template>
            <template #second>{{ t("settings.new_key_sure") }}</template>
          </TwoWords>
        </button>
        <template #tip>
          <span class="info-line">{{ t("settings.encrypt.tip1") }}</span>
          <span class="info-line">{{ t("settings.encrypt.tip2") }}</span>
        </template>
      </ActionRow>
    </SettingsGroup>
    <SettingsGroup v-if="scope === 'settings'" id="update" class="update-check" :title="t('settings.update.group')">
      <UpdateRow
        :running="updateCheck.running.value"
        :outcome="updateCheck.outcome.value"
        @check="updateCheck.check"
        @update="emit('update')"
        @notes="emit('notes')"
      />
    </SettingsGroup>
    <SettingsHelp v-if="scope === 'settings'" />
    <SettingsAbout v-if="scope === 'settings'" />
    <slot></slot>
  </form>
  <p v-else class="empty">{{ t("settings.no_word") }}</p>
</template>
